from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup
import pybind11

# Simple extension without FFmpeg
ext_modules = [
    Pybind11Extension(
        "simple_native",
        ["src/native/simple_test.cpp"],
        include_dirs=[
            pybind11.get_cmake_dir() + "/../../../include",
        ],
        cxx_std=17,
        define_macros=[("VERSION_INFO", '"dev"')],
    ),
]

setup(
    name="simple-native-test",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
) 