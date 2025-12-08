import inspect
from typing import Callable, get_type_hints


class FunctionDependency[**P, R]:
    def __init__(
        self, func: Callable[P, R], dependencies: dict[str, type], return_type: type[R]
    ):
        self.func = func
        self.dependencies = dependencies
        self.return_type = return_type


def analyze_function[**P, R](func: Callable[P, R]):
    hints = get_type_hints(func)
    return_type = hints.get("return", type(None))
    if not return_type:
        raise ValueError("Return type hint is missing")
    sig = inspect.signature(func)
    dependencies = dict[str, type]()
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        if not (param_type := hints.get(param_name)):
            raise ValueError(f"Type hint for parameter '{param_name}' is missing")
        dependencies[param_name] = param_type
    return FunctionDependency(func, dependencies, return_type)
