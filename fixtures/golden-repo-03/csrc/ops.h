#pragma once
#include <torch/extension.h>

torch::Tensor relu_forward_cuda(torch::Tensor x);
torch::Tensor scale_forward_cuda(torch::Tensor x, float scale);
