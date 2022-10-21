#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from abc import ABC
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Type

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream, HttpSubStream


class PhitureBranchStream(HttpStream, ABC):
    url_base = "https://api2.branch.io/v2/"

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        This method should return a Mapping (e.g: dict) containing whatever information required to make paginated requests. This dict is passed
        to most other methods in this class to help you form headers, request bodies, query params, etc..

        For example, if the API accepts a 'page' parameter to determine which page of the result to return, and a response from the API contains a
        'page' number, then this method should probably return a dict {'page': response.json()['page'] + 1} to increment the page count by 1.
        The request_params method should then read the input next_page_token and set the 'page' param to next_page_token['page'].

        :param response: the most recent response from the API
        :return If there is another page in the result, a mapping (e.g: dict) containing information needed to query the next page in the response.
                If there are no more pages in the result, return None.
        """
        return None

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        return {}

    def read_slices_from_records(self, stream, slice_field: str, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        """
        General function for getting parent stream (which should be passed through `stream_class`) slice.
        Generates dicts with `gid` of parent streams.
        """
        stream_slices = stream.stream_slices(sync_mode=SyncMode.full_refresh, cursor_field=slice_field, stream_state={})
        for stream_slice in stream_slices:
            for record in stream.read_records(sync_mode=SyncMode.full_refresh, stream_slice=stream_slice, stream_state={}):
                yield {slice_field: record, **kwargs.get("metadata", {})}


class AggregateExportRequest(PhitureBranchStream):
    primary_key = None
    http_method = "POST"

    max_retries = 10
    retry_factor = 30

    def __init__(
        self, config: Mapping[str, Any], data_source: str, aggregation: str, start_date: str, end_date: str, dimensions: List[str], **kwargs
    ):
        super().__init__(**kwargs)
        self._app_id = config["app_id"]
        self._api_key = config["api_key"]
        self._start_date = pendulum.parse(start_date) if start_date else None
        self._end_date = pendulum.parse(end_date) if end_date else None
        self._data_source = data_source
        self._aggregation = aggregation
        self._dimensions = dimensions

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "analytics"

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "format": "json",
            "app_id": self._app_id,
        }

    def request_body_json(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        return {
            "start_date": self._start_date.to_date_string(),
            "end_date": self._end_date.to_date_string(),
            "data_source": self._data_source,
            "aggregation": self._aggregation,
            "dimensions": self._dimensions,
            "granularity": "day",
            "enable_install_calculation": False,
        }

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        return [response.json()]


class AggregateExportStatus(HttpSubStream, PhitureBranchStream):
    primary_key = None

    max_retries = 100
    retry_factor = 10

    def __init__(
        self,
        config: Mapping[str, Any],
        data_source: str = None,
        aggregation: str = None,
        start_date: str = None,
        end_date: str = None,
        dimensions: List[str] = None,
        **kwargs,
    ):
        super().__init__(
            AggregateExportRequest(
                config=config,
                data_source=data_source,
                aggregation=aggregation,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                **kwargs,
            ),
            **kwargs,
        )
        self._app_id = config["app_id"]
        self._api_key = config["api_key"]

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return f"analytics/{stream_slice['parent']['job_id']}"

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "format": "json",
            "app_id": self._app_id,
        }

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        return [response.json()]

    def should_retry(self, response: requests.Response) -> bool:
        if response.status_code == 429 or 500 <= response.status_code < 600:
            return True
        # check if the response is a json with a status different from "finished" and is not an error
        # what that's mean is that the job is still in progress
        elif response.json().get("status") != "FINISHED" and response.json().get("status") != "ERROR":
            return True
        return False


class AggregateExportDownload(PhitureBranchStream):
    primary_key = ["app_id", "start_date", "end_date", "data_source", "aggregation"]
    cursor_field = "start_date"

    def __init__(self, config: Mapping[str, Any], dimensions: List[str], **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.kwargs = kwargs
        self._app_id = config["app_id"]
        self._api_key = config["api_key"]
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._data_sources = config["data_sources"]
        self._aggregations = config["aggregations"]
        self._dimensions = dimensions

    @property
    def url_base(self) -> str:
        return self._url_base

    @url_base.setter
    def url_base(self, value):
        self._url_base = value

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        self.url_base = stream_slice["parent"]["response_url"]
        return ""

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        date_in_current_stream = pendulum.parse(current_stream_state.get(self.cursor_field, "1970-01-01"))
        date_in_latest_record = pendulum.parse(latest_record.get(self.cursor_field, "1970-01-01"))
        cursor_value = (max(date_in_current_stream, date_in_latest_record)).to_date_string()
        return {self.cursor_field: cursor_value}

    def stream_slices(
        self, sync_mode: SyncMode, cursor_field: List[str] = None, stream_state: Mapping[str, Any] = None
    ) -> Iterable[Optional[Mapping[str, Any]]]:
        start_date = pendulum.parse(self._start_date)
        end_date = pendulum.parse(self._end_date) if self._end_date else pendulum.parse(pendulum.now().to_date_string())

        while start_date <= end_date and start_date <= pendulum.parse(pendulum.now().to_date_string()):
            for data_source in self._data_sources:
                for aggregation in self._aggregations:
                    starting_at = start_date.to_date_string()
                    ending_at = start_date.to_date_string()

                    aggregate_export_status = AggregateExportStatus(
                        config=self.config,
                        data_source=data_source,
                        aggregation=aggregation,
                        start_date=starting_at,
                        end_date=ending_at,
                        dimensions=self._dimensions,
                        **self.kwargs,
                    )
                    yield from aggregate_export_status.read_slices_from_records(
                        stream=aggregate_export_status,
                        slice_field="parent",
                        metadata={
                            "data_source": data_source,
                            "aggregation": aggregation,
                            "start_date": start_date.to_date_string(),
                            "end_date": end_date.to_date_string(),
                            "dimensions": self._dimensions,
                        },
                    )
                    start_date = start_date.add(days=1)

    def parse_response(
        self,
        response: requests.Response,
        *,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        for record in response.json():
            record["app_id"] = self._app_id
            record["start_date"] = stream_slice["start_date"]
            record["end_date"] = stream_slice["end_date"]
            record["data_source"] = stream_slice["data_source"]
            record["aggregation"] = stream_slice["aggregation"]
            yield record


class AggregateExportDownload_1(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_type",
                "last_attributed_touch_data_tilde_advertising_partner_name",
            ],
            **kwargs,
        )


class AggregateExportDownload_2(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_ad_id",
                "last_attributed_touch_data_tilde_ad_name",
            ],
            **kwargs,
        )


class AggregateExportDownload_3(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_ad_set_id",
                "last_attributed_touch_data_tilde_ad_set_name",
            ],
            **kwargs,
        )


class AggregateExportDownload_4(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_ad_set_id",
                "last_attributed_touch_data_tilde_ad_set_name",
            ],
            **kwargs,
        )


class AggregateExportDownload_5(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_campaign",
                "last_attributed_touch_data_tilde_campaign_id",
            ],
            **kwargs,
        )


class AggregateExportDownload_6(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_creative_id",
                "last_attributed_touch_data_tilde_creative_name",
            ],
            **kwargs,
        )


class AggregateExportDownload_7(AggregateExportDownload):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            dimensions=[
                "name",
                "origin",
                "timestamp",
                "from_desktop",
                "first_event_for_user",
                "user_data_geo_country_code",
                "user_data_language",
                "user_data_os",
                "user_data_platform",
                "last_attributed_touch_data_tilde_channel",
                "last_attributed_touch_data_tilde_keyword",
            ],
            **kwargs,
        )
