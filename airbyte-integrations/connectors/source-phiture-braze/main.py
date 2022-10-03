#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from source_phiture_braze import SourcePhitureBraze

if __name__ == "__main__":
    source = SourcePhitureBraze()
    launch(source, sys.argv[1:])
