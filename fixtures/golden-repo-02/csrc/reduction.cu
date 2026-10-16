#include <torch/extension.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include "reduction.h"

// Reduction kernel with limited cub / hipcub
// Scope: Single GPU, reduction, <= 300 LOC
template <typename scalar_t>
__global__ void sum_reduction_kernel(
    const scalar_t* __restrict__ in,
    scalar_t* __restrict__ out,
    int64_t n
) {
    int tid = threadIdx.x;
    int idx = blockIdx.x * blockDim.x + threadIdx.x;

    extern __shared__ char s_mem[];
    scalar_t* s_data = reinterpret_cast<scalar_t*>(s_mem);

    s_data[tid] = (idx < n) ? in[idx] : static_cast<scalar_t>(0);
    __syncthreads();

    for (unsigned int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            s_data[tid] += s_data[tid + s];
        }
        __syncthreads();
    }

    if (tid == 0) {
        atomicAdd(out, s_data[0]);
    }
}

torch::Tensor sum_reduction_cuda(torch::Tensor input) {
    TORCH_CHECK(input.is_cuda(), "input must be a CUDA tensor");
    auto out = torch::zeros({1}, input.options());
    int64_t n = input.numel();
    const int threads = 256;
    const int blocks = (n + threads - 1) / threads;

    AT_DISPATCH_FLOATING_TYPES(input.scalar_type(), "sum_reduction_cuda", ([&] {
        sum_reduction_kernel<scalar_t><<<blocks, threads, threads * sizeof(scalar_t)>>>(
            input.data_ptr<scalar_t>(),
            out.data_ptr<scalar_t>(),
            n
        );
    }));

    cudaError_t err = cudaGetLastError();
    TORCH_CHECK(err == cudaSuccess, "Reduction kernel failed: ", cudaGetErrorString(err));
    return out;
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("sum_reduction", &sum_reduction_cuda, "Sum reduction (CUDA)");
}
