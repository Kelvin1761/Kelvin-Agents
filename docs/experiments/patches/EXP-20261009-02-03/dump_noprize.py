"""同 au_dump_engine_leaves，但模擬 live：今場獎金未知 → class_move 一律 ""。"""
import sys, runpy
sys.path.insert(0, sys.argv[1])
import au_racing_engine.engine_core as ec
ec.today_class_move = lambda race_prize, latest: ""
sys.argv = [sys.argv[1] + "/au_dump_engine_leaves.py", "--out", sys.argv[2]]
runpy.run_path(sys.argv[0], run_name="__main__")
