import re

p = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\src_09m654j._.js'
s = open(p, encoding='utf-8', errors='ignore').read()
print("len:", len(s))

i = s.find('createCipheriv')
print("createCipheriv at", i)
# print a wide window around the crypto module
print(s[max(0,i-4000):i+3000])
