## Convenience script for executing analyze.py multiple times. More like hyperparameter searching..
import subprocess

if __name__ == '__main__':
    min_cost = 0.021 
    max_cost = 0.2
    scaling = 0.003
    
    # run for loop ten times:
    for i in range(5):
        increment = i * scaling
        p = subprocess.Popen(['python3', 'analyze.py', str(min_cost + increment), str(max_cost + increment)])
        # analyze.main(min_cost + increment, max_cost + increment)
        p_status = p.wait()
