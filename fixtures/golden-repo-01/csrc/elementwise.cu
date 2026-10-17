#include "hip/hip_runtime.h"
#include <torch/extension.h>
#include <hip/hip_runtime.h>
#include <hip/hip_runtime.h>
#include "elementwise.h"

// Elementwise Fused Bias + LeakyReLU Kernel
// Compliant with ROCmigrator scope: <= 300 LOC per kernel, elementwise
template <typename scalar_t>
__global__ void fused_bias_leaky_relu_kernel(
    const scalar_t* __restrict__ x,
    const scalar_t* __restrict__ bias,
    scalar_t* __restrict__ out,
    float alpha,
    int64_t numel,
    int64_t bias_size
) {
    int64_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < numel) {
        int64_t b_idx = idx % bias_size;
        scalar_t val = x[idx] + bias[b_idx];
        out[idx] = (val > static_cast<scalar_t>(0)) ? val : val * static_cast<scalar_t>(alpha);
    }
}

torch::Tensor fused_bias_leaky_relu_cuda(
    torch::Tensor x,
    torch::Tensor bias,
    float alpha
) {
    TORCH_CHECK(x.is_cuda(), "x must be a CUDA tensor");
    TORCH_CHECK(bias.is_cuda(), "bias must be a CUDA tensor");
    TORCH_CHECK(x.scalar_type() == bias.scalar_type(), "x and bias must have same dtype");

    auto out = torch::empty_like(x);
    int64_t numel = x.numel();
    int64_t bias_size = bias.numel();

    const int threads = 256;
    const int blocks = (numel + threads - 1) / threads;

    AT_DISPATCH_FLOATING_TYPES(x.scalar_type(), "fused_bias_leaky_relu_cuda", ([&] {
        fused_bias_leaky_relu_kernel<scalar_t><<<blocks, threads>>>(
            x.data_ptr<scalar_t>(),
            bias.data_ptr<scalar_t>(),
            out.data_ptr<scalar_t>(),
            alpha,
            numel,
            bias_size
        );
    }));

    hipError_t err = hipGetLastError();
    TORCH_CHECK(err == hipSuccess, "Kernel failed: ", hipGetErrorString(err));

    return out;
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("forward", &fused_bias_leaky_relu_cuda, "Fused Bias LeakyReLU forward (CUDA)");
}
