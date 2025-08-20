# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
import tempfile

import pexpect
import pytest

PROTOCOL_VERSIONS = [1, 2]
KCONFIG_PARSER_VERSIONS = [1, 2]


def parse_testcases(version):
    with open(f"testcases_v{version}.txt", "r") as f:
        cases = [line for line in f.readlines() if line.strip()]
    if len(cases) % 3 != 0:
        pytest.fail("testcases.txt has wrong number of non-empty lines. Should be 3 lines per test case.")
    for i in range(0, len(cases), 3):
        desc, send, expect_line = cases[i : i + 3]
        assert desc.startswith("* "), f"Unexpected description at line {i + 1}: '{desc}'"
        assert send.startswith("> "), f"Unexpected send at line {i + 2}: '{send}'"
        assert expect_line.startswith("< "), f"Unexpected expect at line {i + 3}: '{expect_line}'"
        yield (desc[2:].strip(), json.loads(send[2:].strip()), json.loads(expect_line[2:].strip()))


def expect_json(p):
    # Expect a JSON object terminated by newline
    p.expect(r"\{.*\}\r?\n")
    return json.loads(p.match.group(0).strip())


def send_request(p, req):
    p.sendline(json.dumps(req))
    return expect_json(p)


def spawn_kconfserver(sdkconfig_path, kconfigs_src, kconfig_projbuilds_src):
    cmd = (
        f"coverage run -m kconfserver "
        f"--env COMPONENT_KCONFIGS_SOURCE_FILE={kconfigs_src} "
        f"--env COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE={kconfig_projbuilds_src} "
        f"--env COMPONENT_KCONFIGS= --env COMPONENT_KCONFIGS_PROJBUILD= "
        f"--kconfig Kconfig --config {sdkconfig_path}"
    )
    # Use spawnu for unicode support
    return pexpect.spawnu(
        re.sub(r" +", " ", cmd),
        timeout=30,
        echo=False,
        use_poll=True,
        env=os.environ.copy(),
    )


@pytest.fixture
def temp_files():
    # Create temporary sdkconfig copy
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp:
        sdkconfig_path = temp.name
        with open("sdkconfig") as orig:
            temp.write(orig.read())

    # Other temp files
    kconfigs_src = tempfile.NamedTemporaryFile(delete=False).name
    kconfig_projbuilds_src = tempfile.NamedTemporaryFile(delete=False).name

    yield sdkconfig_path, kconfigs_src, kconfig_projbuilds_src

    # Cleanup
    for path in (sdkconfig_path, kconfigs_src, kconfig_projbuilds_src):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def server(request, temp_files):
    # request.param provided by parametrized tests
    parser_version = request.param
    os.environ["KCONFIG_PARSER_VERSION"] = str(parser_version)

    sdkconfig_path, kconfigs_src, kconfig_projbuilds_src = temp_files
    p = spawn_kconfserver(sdkconfig_path, kconfigs_src, kconfig_projbuilds_src)

    # Consume banner and initial state
    p.expect(r"Server running.+\r?\n")
    _ = expect_json(p)

    yield p, sdkconfig_path

    # Teardown
    p.sendeof()
    p.expect(pexpect.EOF)
    p.close()


# Parametrize parser_version for all tests that need the server fixture
@pytest.mark.parametrize("server", KCONFIG_PARSER_VERSIONS, indirect=True, ids=["parser-v1", "parser-v2"])
@pytest.mark.parametrize("protocol_version", PROTOCOL_VERSIONS)
def test_protocol_versions(server, protocol_version):
    p, _ = server

    # Load initial state
    send_request(p, {"version": protocol_version, "load": None})

    # Protocol-specific testcases
    for desc, send, expected in parse_testcases(protocol_version):
        resp = send_request(p, {"version": protocol_version, "set": send})
        assert resp.get("version") == protocol_version
        for key, val in expected.items():
            assert resp[key] == val, f"Mismatch in {key}: expected {val}, got {resp[key]}"


@pytest.mark.parametrize("server", KCONFIG_PARSER_VERSIONS, indirect=True)
def test_load_save(server):
    p, sdkconfig_path = server

    before = os.stat(sdkconfig_path).st_mtime
    save_resp = send_request(p, {"version": 2, "save": sdkconfig_path})
    assert "error" not in save_resp
    assert not save_resp["values"]
    assert not save_resp["ranges"]
    assert os.stat(sdkconfig_path).st_mtime > before

    # Test loading in both versions
    load_resp = send_request(p, {"version": 2, "load": sdkconfig_path})
    assert "error" not in load_resp
    assert not load_resp["values"]
    assert not load_resp["ranges"]

    load_resp = send_request(p, {"version": 1, "load": sdkconfig_path})
    assert "error" not in load_resp
    assert load_resp["values"]
    assert load_resp["ranges"]


@pytest.mark.parametrize("server", KCONFIG_PARSER_VERSIONS, indirect=True)
def test_invalid_json(server):
    p, _ = server

    bad = r'{ "version": 2, "load": "c:\\some\\path\\not\\escaped\\as\\json" }'
    p.sendline(bad)
    resp = expect_json(p)
    assert "json" in resp.get("error", [""])[0].lower()

    p.sendline("Hello world!!")
    resp = expect_json(p)
    assert "json" in resp.get("error", [""])[0].lower()
