f = r'C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_0c7dpks._.js'
s = open(f, encoding='utf-8', errors='ignore').read()

i = s.find('998905,e=>')
print('module 998905 at', i)
if i >= 0:
    print(s[i:i+4000])
