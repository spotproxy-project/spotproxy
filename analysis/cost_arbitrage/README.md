## Cost arbitrage pricing history analysis

Ensure all instructions are executed within this folder (`./cost_arbitrage`). 

1. Clone the data source repository:
```bash
git clone https://github.com/ericpauley/aws-spot-price-history.git
```

2. Enter the pricing history month folders and extract any .zst file that you desire. For example:
```bash
cd aws-spot-price-history/prices/2022
unzstd 06.tsv.zst
cd ../../../
```

3. Run the script:
```bash
python3 analyze.py 0.021 0.2
```