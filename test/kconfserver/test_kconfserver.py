# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
import tempfile

import pexpect
import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))  # .../test/kconfserver
_REPO_ROOT = os.path.abspath(os.path.join(_TEST_DIR, "..", ".."))


def _child_env():
    """env for kconfserver subprocess with cwd=test/kconfserver; repo root must be on PYTHONPATH."""
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _REPO_ROOT + (os.pathsep + prev if prev else "")
    return env


PROTOCOL_VERSIONS = [1, 2, 3]
KCONFIG_PARSER_VERSIONS = [1, 2]


def parse_testcases(version):
    with open(os.path.join(_TEST_DIR, f"testcases_v{version}.txt"), "r") as f:
        cases = [line for line in f.readlines() if line.strip()]
    if len(cases) % 3 != 0:
        pytest.fail("testcases.txt has wrong number of non-empty lines. Should be 3 lines per test case.")
    for i in range(0, len(cases), 3):
        desc, send, expect_line = cases[i : i + 3]
        assert desc.startswith("* "), f"Unexpected description at line {i + 1}: '{desc}'"
        if version < 3:
            assert send.startswith("> "), f"Unexpected send at line {i + 2}: '{send}'"
        else:
            assert send.startswith(">R ") or send.startswith("> "), f"Unexpected send at line {i + 2}: '{send}'"
        assert expect_line.startswith("< "), f"Unexpected expect at line {i + 3}: '{expect_line}'"
        yield (
            desc[2:].strip(),
            json.loads(send[2:].strip() if send.startswith("> ") else send[3:]),
            json.loads(expect_line[2:].strip()),
            "set" if send.startswith("> ") else "reset",
        )


def expect_json(p):
    # Expect a JSON object terminated by newline
    p.expect(r"\{.*\}\r?\n")
    return json.loads(p.match.group(0).strip())


def send_request(p, req):
    p.sendline(json.dumps(req))
    return expect_json(p)


def spawn_kconfserver(sdkconfig_path):
    # cwd=test dir so --kconfig Kconfig stays stable; absolute paths change menu node IDs in responses.
    # Empty COMPONENT_*_SOURCE_FILE= matches IDF when no generated kconfigs; test Kconfig does not source them.
    cmd = (
        f"coverage run -m kconfserver "
        f"--env COMPONENT_KCONFIGS_SOURCE_FILE= "
        f"--env COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE= "
        f"--env COMPONENT_KCONFIGS= --env COMPONENT_KCONFIGS_PROJBUILD= "
        f"--kconfig Kconfig --config {sdkconfig_path}"
    )
    # Use spawnu for unicode support
    return pexpect.spawnu(
        re.sub(r" +", " ", cmd),
        timeout=30,
        echo=False,
        use_poll=True,
        cwd=_TEST_DIR,
        env=_child_env(),
    )


@pytest.fixture
def temp_files():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp:
        sdkconfig_path = temp.name
        with open(os.path.join(_TEST_DIR, "sdkconfig")) as orig:
            temp.write(orig.read())

    yield sdkconfig_path

    try:
        os.remove(sdkconfig_path)
    except OSError:
        pass


@pytest.fixture
def server(request, temp_files):
    # request.param provided by parametrized tests
    parser_version = request.param
    os.environ["KCONFIG_PARSER_VERSION"] = str(parser_version)

    sdkconfig_path = temp_files
    p = spawn_kconfserver(sdkconfig_path)

    # Consume banner and initial state
    p.expect(r"Server running.+\r?\n")
    initial_resp = expect_json(p)

    yield p, sdkconfig_path, initial_resp

    # Teardown
    p.sendeof()
    p.expect(pexpect.EOF)
    p.close()


# Parametrize parser_version for all tests that need the server fixture
@pytest.mark.parametrize(
    "server", KCONFIG_PARSER_VERSIONS, indirect=True, ids=[f"parser-v{v}" for v in KCONFIG_PARSER_VERSIONS]
)
@pytest.mark.parametrize("protocol_version", PROTOCOL_VERSIONS, ids=[f"protocol-v{v}" for v in PROTOCOL_VERSIONS])
def test_protocol_versions(server, protocol_version):
    p, _, _ = server

    # Load initial state
    send_request(p, {"version": protocol_version, "load": None})

    # Protocol-specific testcases
    for desc, send, expected, command in parse_testcases(protocol_version):
        resp = send_request(p, {"version": protocol_version, f"{command}": send})
        assert resp.get("version") == protocol_version
        for key, val in expected.items():
            assert resp[key] == val, f"Mismatch in {key} ({desc}): expected {val}, got {resp[key]}"


@pytest.mark.parametrize(
    "server", KCONFIG_PARSER_VERSIONS, indirect=True, ids=[f"parser-v{v}" for v in KCONFIG_PARSER_VERSIONS]
)
@pytest.mark.parametrize("protocol_version", PROTOCOL_VERSIONS, ids=[f"protocol-v{v}" for v in PROTOCOL_VERSIONS])
def test_load_save(server, protocol_version):
    p, sdkconfig_path, _ = server

    before = os.stat(sdkconfig_path).st_mtime
    save_resp = send_request(p, {"version": protocol_version, "save": sdkconfig_path})
    assert "error" not in save_resp
    assert not save_resp["values"]
    assert not save_resp["ranges"]
    assert os.stat(sdkconfig_path).st_mtime > before

    load_resp = send_request(p, {"version": protocol_version, "load": sdkconfig_path})
    assert "error" not in load_resp
    if protocol_version > 1:
        assert not load_resp["values"]
        assert not load_resp["ranges"]
    else:
        assert load_resp["values"]
        assert load_resp["ranges"]


@pytest.mark.parametrize(
    "server", KCONFIG_PARSER_VERSIONS, indirect=True, ids=[f"parser-v{v}" for v in KCONFIG_PARSER_VERSIONS]
)
@pytest.mark.parametrize("protocol_version", PROTOCOL_VERSIONS, ids=[f"protocol-v{v}" for v in PROTOCOL_VERSIONS])
def test_invalid_json(server, protocol_version):
    p, _, _ = server

    bad = rf'{{ "version": {protocol_version}, "load": "c:\\some\\path\\not\\escaped\\as\\json" }}'
    p.sendline(bad)
    resp = expect_json(p)
    assert "json" in resp.get("error", [""])[0].lower()

    p.sendline("Hello world!!")
    resp = expect_json(p)
    assert "json" in resp.get("error", [""])[0].lower()


@pytest.mark.parametrize(
    "server", KCONFIG_PARSER_VERSIONS, indirect=True, ids=[f"parser-v{v}" for v in KCONFIG_PARSER_VERSIONS]
)
def test_warnings(server):
    """
    The "warnings" key is returned only in the initial response,
    which is not checked in other tests, thus standalone test case.
    """
    _, _, initial_resp = server
    assert "warnings" in initial_resp
    warnings = initial_resp["warnings"]
    assert "DANGEROUS_OPTION" in warnings, print(warnings)
    assert warnings["DANGEROUS_OPTION"] == "This is a warning for DANGEROUS_OPTION"
