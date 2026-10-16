#pragma once
#include <torch/extension.h>

torch::Tensor fused_bias_leaky_relu_cuda(
    torch::Tensor x,
    torch::Tensor bias,
    float alpha
);
