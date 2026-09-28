import sys
sys.path.insert(0, r'D:\omniroute-monetizer\scripts\automation')
from replay_check import classify

t1 = classify('data: {"type": "project_start"} keepalive events and prose mentioning credits limits', 200, None)
assert t1[0] == 'PIPELINE', t1
t2 = classify('your quota is exhausted, upgrade now', 200, None)
assert t2[0] == 'WALL', t2
t3 = classify('auth rejected: unauthorized', None, None)
assert t3[0] == 'AUTH', t3
t4 = classify('plain reply with no markers and no 58', 200, None)
assert t4[0] == 'NO_ANSWER', t4
print('classifier tests: 4/4 PASS (pure logic)')
print('t1 detail:', t1[1])
