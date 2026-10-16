"""
agent_orchestrator/torch_compat.py — PyTorch Compatibility Layer.
Uses native torch if PyTorch is installed on the system.
Provides a transparent compatibility bridge using numpy for local development /
mock environments (Windows native) where PyTorch is not installed,
executing numerical verification accurately and mathematically.
"""

import sys

try:
    import torch as _torch
    torch = _torch
except ImportError:
    import numpy as np

    class MockTensor:
        def __init__(self, data, dtype=np.float32):
            if isinstance(data, MockTensor):
                self._data = data._data.copy()
            elif isinstance(data, np.ndarray):
                self._data = data
            else:
                self._data = np.array(data, dtype=dtype)

        @property
        def shape(self):
            return list(self._data.shape)

        @property
        def dtype(self):
            return self._data.dtype

        def numel(self) -> int:
            return int(self._data.size)

        def cpu(self):
            return self

        def is_cuda(self) -> bool:
            return False

        def scalar_type(self):
            return str(self._data.dtype)

        def item(self):
            return self._data.item()

        def sum(self):
            return MockTensor(self._data.sum())

        def any(self):
            return MockTensor(self._data.any())

        def all(self):
            return MockTensor(self._data.all())

        def __add__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data + val)

        def __radd__(self, other):
            return self.__add__(other)

        def __sub__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data - val)

        def __rsub__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(val - self._data)

        def __mul__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data * val)

        def __rmul__(self, other):
            return self.__mul__(other)

        def __truediv__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data / val)

        def __gt__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data > val)

        def __lt__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data < val)

        def __ge__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data >= val)

        def __le__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data <= val)

        def __repr__(self):
            return f"MockTensor({self._data})"

    class TestingModule:
        @staticmethod
        def assert_close(actual, expected, rtol=1e-5, atol=1e-8):
            a = actual._data if isinstance(actual, MockTensor) else actual
            e = expected._data if isinstance(expected, MockTensor) else expected
            np.testing.assert_allclose(a, e, rtol=rtol, atol=atol)

    class TorchShim:
        Tensor = MockTensor
        float32 = np.float32
        float64 = np.float64
        testing = TestingModule()

        @staticmethod
        def manual_seed(seed: int):
            np.random.seed(seed)

        @staticmethod
        def randn(*shape, dtype=np.float32, device="cpu"):
            if len(shape) == 1 and isinstance(shape[0], (list, tuple)):
                shape = tuple(shape[0])
            arr = np.random.randn(*shape).astype(dtype)
            return MockTensor(arr)

        @staticmethod
        def where(cond, x, y):
            c = cond._data if isinstance(cond, MockTensor) else cond
            xv = x._data if isinstance(x, MockTensor) else x
            yv = y._data if isinstance(y, MockTensor) else y
            return MockTensor(np.where(c, xv, yv))

        @staticmethod
        def abs(x):
            val = x._data if isinstance(x, MockTensor) else x
            return MockTensor(np.abs(val))

        @staticmethod
        def max(x):
            val = x._data if isinstance(x, MockTensor) else x
            return MockTensor(np.max(val))

        @staticmethod
        def isnan(x):
            val = x._data if isinstance(x, MockTensor) else x
            return MockTensor(np.isnan(val))

        @staticmethod
        def isinf(x):
            val = x._data if isinstance(x, MockTensor) else x
            return MockTensor(np.isinf(val))

        @staticmethod
        def equal(x, y):
            a = x._data if isinstance(x, MockTensor) else x
            b = y._data if isinstance(y, MockTensor) else y
            return bool(np.array_equal(a, b))

        @staticmethod
        def empty_like(x):
            val = x._data if isinstance(x, MockTensor) else x
            return MockTensor(np.empty_like(val))

    torch = TorchShim()
