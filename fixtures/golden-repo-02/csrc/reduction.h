#pragma once
#include <torch/extension.h>

torch::Tensor sum_reduction_cuda(torch::Tensor input);
