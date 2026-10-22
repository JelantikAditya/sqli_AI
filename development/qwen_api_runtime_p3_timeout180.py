"""P3 v4 transport adapter with a separate bounded analysis timeout.

P2's frozen settings remain unchanged. The analysis request envelope is built
from the same P2 ChatSettings, then the local transport timeout is extended.
The timeout is local to urllib and is not included in the API payload.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from qwen_api_client import QwenAPIClient
from qwen_api_p2_analysis import default_settings as p2_analysis_settings
from qwen_api_runtime import CheckpointedQwenAPI


MAX_TRANSPORT_TIMEOUT_SECONDS = 180


class Timeout180CheckpointedQwenAPI(CheckpointedQwenAPI):
    """Use 90 seconds for generation and 180 seconds for P3 analysis calls."""

    def __init__(self, api_key: str, experiment_directory: Path, config: dict,
                 *, analysis_timeout_seconds: int = MAX_TRANSPORT_TIMEOUT_SECONDS):
        if type(analysis_timeout_seconds) is not int or not 90 <= analysis_timeout_seconds <= MAX_TRANSPORT_TIMEOUT_SECONDS:
            raise ValueError("P3 analysis timeout must be an integer from 90 to 180 seconds.")

        # Initialize the existing adapter against its unchanged P2-compatible
        # 90-second profile, then override only the local analysis transport wait.
        super().__init__(api_key, experiment_directory, config)
        frozen_p2_settings = p2_analysis_settings()
        if self.settings["analysis"] != frozen_p2_settings:
            raise ValueError("P3 analysis request options differ from the frozen P2 profile.")

        analysis_settings = replace(frozen_p2_settings, timeout_seconds=analysis_timeout_seconds)
        self.settings["analysis"] = analysis_settings
        self.client["analysis"] = QwenAPIClient(self.api_key, settings=analysis_settings)
