import faulthandler
faulthandler.enable()
from aiodeepseek.pow import _pow
print('Calling solve...')
_pow.solve('14391f1eeeafaed16477', '1251aa9c51a85fe4bedceed9ac7e1adef0900fc4e5892acb6035680c3a4fc705', 2500000)
print('Done!')
