#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional, Type, Union

from airbyte_cdk.sources.declarative.interpolation import InterpolatedString
from airbyte_cdk.sources.declarative.requesters.request_options import InterpolatedRequestOptionsProvider
from airbyte_cdk.sources.declarative.types import StreamSlice, StreamState


@dataclass
class GraphQLRequestOptionsProvider(InterpolatedRequestOptionsProvider):
    NEXT_PAGE_TOKEN_FIELD_NAME = "next_page_token"
    NESTED_OBJECTS_LIMIT_MAX_VALUE = 100

    limit: Union[InterpolatedString, str, int] = None

    def __post_init__(self, options: Mapping[str, Any]):
        super(GraphQLRequestOptionsProvider, self).__post_init__(options)

        self.limit = InterpolatedString.create(self.limit, options=options)
        self.name = options.get("name", "").lower()

    def _ensure_type(self, t: Type, o: Any):
        """
        Ensure given object `o` is of type `t`
        """
        if not isinstance(o, t):
            raise TypeError(f"{type(o)} {o} is not of type {t}")

    def _get_schema_root_properties(self):
        schema_path = os.path.join(os.path.abspath(os.curdir), "source_monday", f"schemas/{self.name}.json")
        with open(schema_path) as f:
            schema_dict = json.load(f)
            return schema_dict["properties"]

    def _get_object_arguments(self, **object_arguments) -> str:
        return ",".join([f"{argument}:{value}" for argument, value in object_arguments.items() if value is not None])

    def _build_query(self, object_name: str, field_schema: dict, **object_arguments) -> str:
        """
        Recursive function that builds a GraphQL query string by traversing given stream schema properties.
        Attributes
            object_name (str): the name of root object
            field_schema (dict): configured catalog schema for current stream
            object_arguments (dict): arguments such as limit, page, ids, ... etc to be passed for given object
        """
        fields = []
        for field, nested_schema in field_schema.items():
            nested_fields = nested_schema.get("properties", nested_schema.get("items", {}).get("properties"))
            if nested_fields:
                # preconfigured_arguments = get properties from schema or any other source ...
                # fields.append(self._build_query(field, nested_fields, **preconfigured_arguments))
                fields.append(self._build_query(field, nested_fields))
            else:
                fields.append(field)

        arguments = self._get_object_arguments(**object_arguments)
        arguments = f"({arguments})" if arguments else ""
        fields = ",".join(fields)

        return f"{object_name}{arguments}{{{fields}}}"

    def _build_items_query(self, object_name: str, field_schema: dict, **object_arguments) -> str:
        """
        Special optimization needed for items stream. Starting October 3rd, 2022 items can only be reached through boards.
        See https://developer.monday.com/api-reference/docs/items-queries#items-queries
        """
        query = self._build_query(object_name, field_schema, limit=self.NESTED_OBJECTS_LIMIT_MAX_VALUE)
        arguments = self._get_object_arguments(**object_arguments)
        return f"boards({arguments}){{{query}}}"

    def _build_teams_query(self, object_name: str, field_schema: dict, **object_arguments) -> str:
        """
        Special optimization needed for tests to pass successfully because of rate limits.
        It makes a query cost less points and should not be used to production
        """
        teams_limit = self.config.get("teams_limit")
        if teams_limit:
            self._ensure_type(int, teams_limit)
            arguments = self._get_object_arguments(**object_arguments)
            query = f"{{id,name,picture_url,users(limit:{teams_limit}){{id}}}}"
            return f"{object_name}({arguments}){query}"
        return self._build_query(object_name=object_name, field_schema=field_schema, **object_arguments)

    def get_request_params(
        self,
        *,
        stream_state: Optional[StreamState] = None,
        stream_slice: Optional[StreamSlice] = None,
        next_page_token: Optional[Mapping[str, Any]] = None,
    ) -> MutableMapping[str, Any]:
        """
        Combines queries to a single GraphQL query.
        """
        limit = self.limit.eval(self.config)
        if self.name == "items":
            query_builder = self._build_items_query
        elif self.name == "teams":
            query_builder = self._build_teams_query
        else:
            query_builder = self._build_query
        query = query_builder(
            object_name=self.name,
            field_schema=self._get_schema_root_properties(),
            limit=limit or None,
            page=next_page_token and next_page_token[self.NEXT_PAGE_TOKEN_FIELD_NAME],
        )
        return {"query": f"query{{{query}}}"}
