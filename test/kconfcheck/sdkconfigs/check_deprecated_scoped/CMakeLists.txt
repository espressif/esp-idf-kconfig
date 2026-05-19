cmake_minimum_required(VERSION 3.22)

if(CMAKE_CURRENT_LIST_DIR STREQUAL CMAKE_SOURCE_DIR)
    message(FATAL_ERROR "Not buildable directly.")
endif()

project(esp-idf C CXX ASM)
