#!/bin/bash

source ~/.bashrc
conda activate

conda build --variants '{"numpy": ["1.19", "1.18", "1.17", "1.16"], "python": ["3.8"]}' recipe || exit 1
conda build --variants '{"numpy": ["1.19", "1.18", "1.17", "1.16", "1.15"], "python": ["3.7"]}' recipe || exit 1
