conda activate

conda build --variants "{\"numpy\": [\"1.15\", \"1.14\"], \"python\": [\"3.6\"]}" recipe || exit 1
conda build --variants "{\"numpy\": [\"1.17\", \"1.16\", \"1.15\"], \"python\": [\"3.7\"]}" recipe || exit 1
conda build --variants "{\"numpy\": [\"1.17\", \"1.16\"], \"python\": [\"3.8\"]}" recipe || exit 1
