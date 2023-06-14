#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from abc import ABC
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream

from source_phiture_adjust.fields import (
    ad_spend_metrics_list,
    conversion_metrics_list,
    dimensions,
    revenue_metrics_list,
    skad_metrics_list,
)


class ReportService(HttpStream, ABC):
    url_base = "https://dash.adjust.com"

    primary_key = None
    cursor_field = "day"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000
    # the window attribution is used to re-fetch the last 30 days of data
    #  only if the last state day is in the range of the last 30 days
    window_attribution = {"days": 30}

    def __init__(self, config: Mapping[str, Any], dimensions: List[str], metrics: List[str], **kwargs):
        super().__init__(**kwargs)
        self._app_token = config["app_token"]
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._attribution_type = config.get("attribution_type")
        self._attribution_source = config.get("attribution_source")
        self._ad_spend_mode = config.get("ad_spend_mode")
        self._cohort_maturity = config.get("cohort_maturity")
        self._currency = config.get("currency")
        self._dimensions = dimensions
        self._metrics = metrics

        self.primary_key = dimensions

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "control-center/reports-service/report"

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "app_token__in": self._app_token,
            "date_period": f'{stream_slice["start_date"]}:{stream_slice["end_date"]}',
            "dimensions": ",".join(self._dimensions),
            "metrics": ",".join(self._metrics),
            "attribution_type": self._attribution_type,
            "ad_spend_mode": self._ad_spend_mode,
            "currency": self._currency,
            "utc_offset": "+00:00",
        }

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        data = response.json()
        for row in data["rows"]:
            # for each key in the row, replace the space with underscore
            # this is happening because some of the events have spaces in their names
            # avoid: RuntimeError: dictionary keys changed during iteration
            yield {key.replace(" ", "_"): value for key, value in row.items()}

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        # Initialize stream state to an empty dictionary if not provided.
        stream_state = stream_state or {}

        # If the stream state includes the cursor field, use it to determine the starting date for the time window.
        if stream_state.get(self.cursor_field):
            start_date = pendulum.parse(stream_state[self.cursor_field])

            # If the starting date falls within the attribution window, adjust it to the beginning of the window.
            if pendulum.now().subtract(**self.window_attribution) < start_date < pendulum.now():
                start_date = pendulum.parse(stream_state[self.cursor_field]).subtract(**self.window_attribution)
        else:
            # Otherwise, use the start date provided during initialization.
            start_date = pendulum.parse(self._start_date)

        # Determine the end date for the time window.
        end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

        while start_date <= end_date and start_date < pendulum.parse(pendulum.now().to_date_string()):
            starting_at = start_date
            ending_at = start_date

            self.logger.info(f"Fetching {self.name} ; time range: {starting_at.to_date_string()} - {ending_at.to_date_string()}")

            # yield a single dictionary for the time window.
            yield {
                "start_date": starting_at.to_date_string(),
                "end_date": ending_at.to_date_string(),
            }

            # Increment the start date by the time interval between windows.
            start_date = start_date.add(**self.time_interval)

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]):
        current_stream_state = current_stream_state or {}
        current_stream_state[self.cursor_field] = pendulum.parse(latest_record[self.cursor_field]).to_date_string()
        return current_stream_state


class ReportServiceConversionMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=conversion_metrics_list, **kwargs)


class ReportServiceAdSpendMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=ad_spend_metrics_list, **kwargs)


class ReportServiceRevenueMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=revenue_metrics_list, **kwargs)


class ReportServiceSkadMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=skad_metrics_list, **kwargs)


class ReportServiceEventMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        events = config.get("additional_metrics", [])
        event_metrics_suffix = [
            "events",
            "events_min",
            "events_max",
            "events_est",
            "revenue",
            "revenue_min",
            "revenue_max",
            "revenue_est",
        ]
        # for each metric name in the list of events
        # - add a suffix to it
        # - strip
        # - lower
        # IMPORTANT: do not replace space with underscore here
        # this will be happening in the get_json_schema method
        # and in the parse_response method
        self.event_metrics_list = [f"{metric.strip().lower()}_{suffix}" for metric in events for suffix in event_metrics_suffix]
        super().__init__(config, dimensions=dimensions, metrics=self.event_metrics_list, **kwargs)

    def get_json_schema(self):
        """
        Compose json schema based on user defined event metrics.
        """

        local_json_schema = {
            "$schema": "http://json-schema.org/schema#",
            "type": "object",
            "properties": {},
        }

        fields = dimensions + self.event_metrics_list
        fields = sorted(fields)

        for field in fields:
            # for each field, replace the space with underscore
            # this is happening because some of the events have spaces in their names
            local_json_schema["properties"][field.replace(" ", "_")] = {"type": ["null", "string"]}

        return local_json_schema
