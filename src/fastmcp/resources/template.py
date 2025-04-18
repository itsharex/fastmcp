"""Resource template functionality."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter, validate_call

from fastmcp.resources.types import FunctionResource, Resource
from fastmcp.utilities.types import _convert_set_defaults


class MyModel(BaseModel):
    key: str
    value: int


class ResourceTemplate(BaseModel):
    """A template for dynamically creating resources."""

    uri_template: str = Field(
        description="URI template with parameters (e.g. weather://{city}/current)"
    )
    name: str = Field(description="Name of the resource")
    description: str | None = Field(description="Description of what the resource does")
    tags: Annotated[set[str], BeforeValidator(_convert_set_defaults)] = Field(
        default_factory=set, description="Tags for the resource"
    )
    mime_type: str = Field(
        default="text/plain", description="MIME type of the resource content"
    )
    fn: Callable[..., Any]
    parameters: dict[str, Any] = Field(
        description="JSON schema for function parameters"
    )

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        uri_template: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        tags: set[str] | None = None,
    ) -> ResourceTemplate:
        """Create a template from a function."""
        func_name = name or fn.__name__
        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        # Validate that URI params match function params
        uri_params = set(re.findall(r"{(\w+)}", uri_template))
        if not uri_params:
            raise ValueError("URI template must contain at least one parameter")

        func_params = set(inspect.signature(fn).parameters.keys())

        # get the parameters that are required
        required_params = {
            p
            for p in func_params
            if inspect.signature(fn).parameters[p].default is inspect.Parameter.empty
        }

        if not required_params.issubset(uri_params):
            raise ValueError(
                f"URI parameters {uri_params} must be a subset of the required function arguments: {required_params}"
            )

        if not uri_params.issubset(func_params):
            raise ValueError(
                f"URI parameters {uri_params} must be a subset of the function arguments: {func_params}"
            )

        # Get schema from TypeAdapter - will fail if function isn't properly typed
        parameters = TypeAdapter(fn).json_schema()

        # ensure the arguments are properly cast
        fn = validate_call(fn)

        return cls(
            uri_template=uri_template,
            name=func_name,
            description=description or fn.__doc__ or "",
            mime_type=mime_type or "text/plain",
            fn=fn,
            parameters=parameters,
            tags=tags or set(),
        )

    def matches(self, uri: str) -> dict[str, Any] | None:
        """Check if URI matches template and extract parameters."""
        # Convert template to regex pattern
        pattern = self.uri_template.replace("{", "(?P<").replace("}", ">[^/]+)")
        match = re.match(f"^{pattern}$", uri)
        if match:
            return match.groupdict()
        return None

    async def create_resource(self, uri: str, params: dict[str, Any]) -> Resource:
        """Create a resource from the template with the given parameters."""
        try:
            # Call function and check if result is a coroutine
            result = self.fn(**params)
            if inspect.iscoroutine(result):
                result = await result

            return FunctionResource(
                uri=uri,  # type: ignore
                name=self.name,
                description=self.description,
                mime_type=self.mime_type,
                fn=lambda: result,  # Capture result in closure
                tags=self.tags,
            )
        except Exception as e:
            raise ValueError(f"Error creating resource from template: {e}")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResourceTemplate):
            return False
        return self.model_dump() == other.model_dump()
