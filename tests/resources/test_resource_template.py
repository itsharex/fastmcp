import json

import pytest
from pydantic import BaseModel

from fastmcp.resources import FunctionResource, ResourceTemplate


class TestResourceTemplate:
    """Test ResourceTemplate functionality."""

    def test_template_creation(self):
        """Test creating a template from a function."""

        def my_func(key: str, value: int) -> dict:
            return {"key": key, "value": value}

        template = ResourceTemplate.from_function(
            fn=my_func,
            uri_template="test://{key}/{value}",
            name="test",
        )
        assert template.uri_template == "test://{key}/{value}"
        assert template.name == "test"
        assert template.mime_type == "text/plain"  # default
        test_input = {"key": "test", "value": 42}
        assert template.fn(**test_input) == my_func(**test_input)

    def test_template_matches(self):
        """Test matching URIs against a template."""

        def my_func(key: str, value: int) -> dict:
            return {"key": key, "value": value}

        template = ResourceTemplate.from_function(
            fn=my_func,
            uri_template="test://{key}/{value}",
            name="test",
        )

        # Valid match
        params = template.matches("test://foo/123")
        assert params == {"key": "foo", "value": "123"}

        # No match
        assert template.matches("test://foo") is None
        assert template.matches("other://foo/123") is None

    def test_template_uri_validation(self):
        """Test validation rule: URI template must have at least one parameter."""

        def my_func() -> dict:
            return {"data": "value"}

        with pytest.raises(
            ValueError, match="URI template must contain at least one parameter"
        ):
            ResourceTemplate.from_function(
                fn=my_func,
                uri_template="test://no-params",
                name="test",
            )

    def test_template_uri_params_subset_of_function_params(self):
        """Test validation rule: URI parameters must be a subset of function parameters."""

        def my_func(key: str, value: int) -> dict:
            return {"key": key, "value": value}

        # This should work - URI params are a subset of function params
        template = ResourceTemplate.from_function(
            fn=my_func,
            uri_template="test://{key}/{value}",
            name="test",
        )
        assert template.uri_template == "test://{key}/{value}"

        # This should fail - 'unknown' is not a function parameter
        with pytest.raises(
            ValueError,
            match="URI parameters .* must be a subset of the required function arguments",
        ):
            ResourceTemplate.from_function(
                fn=my_func,
                uri_template="test://{key}/{unknown}",
                name="test",
            )

    def test_required_params_subset_of_uri_params(self):
        """Test validation rule: Required function parameters must be in URI parameters."""

        # Function with required parameters
        def func_with_required(
            required_param: str, optional_param: str = "default"
        ) -> dict:
            return {"required": required_param, "optional": optional_param}

        # This should work - required param is in URI
        template = ResourceTemplate.from_function(
            fn=func_with_required,
            uri_template="test://{required_param}",
            name="test",
        )
        assert template.uri_template == "test://{required_param}"

        # This should fail - required param is not in URI
        with pytest.raises(
            ValueError,
            match="URI parameters .* must be a subset of the required function arguments",
        ):
            ResourceTemplate.from_function(
                fn=func_with_required,
                uri_template="test://{optional_param}",
                name="test",
            )

    def test_multiple_required_params(self):
        """Test validation with multiple required parameters."""

        def multi_required(param1: str, param2: int, optional: str = "default") -> dict:
            return {"p1": param1, "p2": param2, "opt": optional}

        # This works - all required params in URI
        template = ResourceTemplate.from_function(
            fn=multi_required,
            uri_template="test://{param1}/{param2}",
            name="test",
        )
        assert template.uri_template == "test://{param1}/{param2}"

        # This fails - missing one required param
        with pytest.raises(
            ValueError,
            match="URI parameters .* must be a subset of the required function arguments",
        ):
            ResourceTemplate.from_function(
                fn=multi_required,
                uri_template="test://{param1}",
                name="test",
            )

    @pytest.mark.anyio
    async def test_create_resource(self):
        """Test creating a resource from a template."""

        def my_func(key: str, value: int) -> dict:
            return {"key": key, "value": value}

        template = ResourceTemplate.from_function(
            fn=my_func,
            uri_template="test://{key}/{value}",
            name="test",
        )

        resource = await template.create_resource(
            "test://foo/123",
            {"key": "foo", "value": 123},
        )

        assert isinstance(resource, FunctionResource)
        content = await resource.read()
        assert isinstance(content, str)
        data = json.loads(content)
        assert data == {"key": "foo", "value": 123}

    @pytest.mark.anyio
    async def test_template_error(self):
        """Test error handling in template resource creation."""

        def failing_func(x: str) -> str:
            raise ValueError("Test error")

        template = ResourceTemplate.from_function(
            fn=failing_func,
            uri_template="fail://{x}",
            name="fail",
        )

        with pytest.raises(ValueError, match="Error creating resource from template"):
            await template.create_resource("fail://test", {"x": "test"})

    @pytest.mark.anyio
    async def test_async_text_resource(self):
        """Test creating a text resource from async function."""

        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        template = ResourceTemplate.from_function(
            fn=greet,
            uri_template="greet://{name}",
            name="greeter",
        )

        resource = await template.create_resource(
            "greet://world",
            {"name": "world"},
        )

        assert isinstance(resource, FunctionResource)
        content = await resource.read()
        assert content == "Hello, world!"

    @pytest.mark.anyio
    async def test_async_binary_resource(self):
        """Test creating a binary resource from async function."""

        async def get_bytes(value: str) -> bytes:
            return value.encode()

        template = ResourceTemplate.from_function(
            fn=get_bytes,
            uri_template="bytes://{value}",
            name="bytes",
        )

        resource = await template.create_resource(
            "bytes://test",
            {"value": "test"},
        )

        assert isinstance(resource, FunctionResource)
        content = await resource.read()
        assert content == b"test"

    @pytest.mark.anyio
    async def test_basemodel_conversion(self):
        """Test handling of BaseModel types."""

        class MyModel(BaseModel):
            key: str
            value: int

        def get_data(key: str, value: int) -> MyModel:
            return MyModel(key=key, value=value)

        template = ResourceTemplate.from_function(
            fn=get_data,
            uri_template="test://{key}/{value}",
            name="test",
        )

        resource = await template.create_resource(
            "test://foo/123",
            {"key": "foo", "value": 123},
        )

        assert isinstance(resource, FunctionResource)
        content = await resource.read()
        assert isinstance(content, str)
        data = json.loads(content)
        assert data == {"key": "foo", "value": 123}

    @pytest.mark.anyio
    async def test_custom_type_conversion(self):
        """Test handling of custom types."""

        class CustomData:
            def __init__(self, value: str):
                self.value = value

            def __str__(self) -> str:
                return self.value

        def get_data(value: str) -> CustomData:
            return CustomData(value)

        template = ResourceTemplate.from_function(
            fn=get_data,
            uri_template="test://{value}",
            name="test",
        )

        resource = await template.create_resource(
            "test://hello",
            {"value": "hello"},
        )

        assert isinstance(resource, FunctionResource)
        content = await resource.read()
        assert content == "hello"
