#include <torch/extension.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include "ops.h"

template <typename scalar_t>
__global__ void scale_kernel(const scalar_t* in, scalar_t* out, float scale, int64_t n) {
    int64_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        out[idx] = in[idx] * static_cast<scalar_t>(scale);
    }
}

torch::Tensor scale_forward_cuda(torch::Tensor x, float scale) {
    auto out = torch::empty_like(x);
    int64_t n = x.numel();
    const int threads = 256;
    const int blocks = (n + threads - 1) / threads;

    AT_DISPATCH_FLOATING_TYPES(x.scalar_type(), "scale_forward_cuda", ([&] {
        scale_kernel<scalar_t><<<blocks, threads>>>(x.data_ptr<scalar_t>(), out.data_ptr<scalar_t>(), scale, n);
    }));
    return out;
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("relu", &relu_forward_cuda, "ReLU forward (CUDA)");
    m.def("scale", &scale_forward_cuda, "Scale forward (CUDA)");
}
