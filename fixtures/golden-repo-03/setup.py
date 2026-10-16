import os
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

# ROCmigrator Golden Repo 03: Multi-kernel setup.py
setup(
    name="multikernel_ops",
    ext_modules=[
        CUDAExtension(
            name="multikernel_cuda",
            sources=[
                "csrc/relu.cu",
                "csrc/scale.cu",
            ],
            extra_compile_args={
                "cxx": ["-O3"],
                "nvcc": ["-O3"],
            },
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
