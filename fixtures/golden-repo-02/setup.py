import os
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

# ROCmigrator Golden Repo 02: Reduction with limited hipCUB
setup(
    name="reduction_ops",
    ext_modules=[
        CUDAExtension(
            name="reduction_cuda",
            sources=["csrc/reduction.cu"],
            extra_compile_args={
                "cxx": ["-O3"],
                "nvcc": ["-O3"],
            },
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
