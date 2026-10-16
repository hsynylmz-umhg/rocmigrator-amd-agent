import os
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

# ROCmigrator Golden Repo 01: Elementwise Fused Bias LeakyReLU CUDAExtension
setup(
    name="fused_elementwise",
    ext_modules=[
        CUDAExtension(
            name="fused_elementwise_cuda",
            sources=[
                "csrc/elementwise.cu",
            ],
            extra_compile_args={
                "cxx": ["-O3"],
                "nvcc": ["-O3"],
            },
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
