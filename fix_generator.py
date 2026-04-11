import ag_wong_choi_analyst
import os

def fixed_generate_race_logic(target_dir, r):
    facts_file = os.path.join(target_dir, f"04-12_ShaTin Race {r} Facts.md")
    if not os.path.exists(facts_file):
        return False
        
    dist, cls = ag_wong_choi_analyst.get_track_distance(facts_file)
    horses = ag_wong_choi_analyst.get_horses(facts_file)
    # the rest of the generation ...
    
