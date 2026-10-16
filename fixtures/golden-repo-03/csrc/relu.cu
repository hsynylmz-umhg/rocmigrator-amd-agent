#include <torch/extension.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include "ops.h"

template <typename scalar_t>
__global__ void relu_kernel(const scalar_t* in, scalar_t* out, int64_t n) {
    int64_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        scalar_t val = in[idx];
        out[idx] = val > static_cast<scalar_t>(0) ? val : static_cast<scalar_t>(0);
    }
}

torch::Tensor relu_forward_cuda(torch::Tensor x) {
    auto out = torch::empty_like(x);
    int64_t n = x.numel();
    const int threads = 256;
    const int blocks = (n + threads - 1) / threads;

    AT_DISPATCH_FLOATING_TYPES(x.scalar_type(), "relu_forward_cuda", ([&] {
        relu_kernel<scalar_t><<<blocks, threads>>>(x.data_ptr<scalar_t>(), out.data_ptr<scalar_t>(), n);
    }));
    return out;
}
