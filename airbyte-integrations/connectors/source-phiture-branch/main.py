#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from source_phiture_branch import SourcePhitureBranch

if __name__ == "__main__":
    source = SourcePhitureBranch()
    launch(source, sys.argv[1:])
