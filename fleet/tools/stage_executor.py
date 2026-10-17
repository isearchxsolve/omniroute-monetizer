"""Compile-gate an isolated CPU executor artifact without running its generator."""
import ast,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
stage=ROOT/'state'/'recovery_20261017_staged'
guard=(ROOT/'fleet/kernels/queue_job_guard.py').read_text(encoding='utf-8')
items={'cloud':('gen_cloud_cell.py','omniroute-cloud-cell','omniroute-cloud-cell-cpu-worker'),'playwright':('gen_playwright.py','omniroute-playwright','omniroute-playwright-executor')}
for name in sys.argv[1:] or items:
 gen,dirname,slug=items[name]
 tree=ast.parse((ROOT/'fleet/kernels'/gen).read_text(encoding='utf-8'))
 values={}
 for node in tree.body:
  if isinstance(node,ast.Assign) and isinstance(node.value,(ast.Constant,ast.List)):
   for target in node.targets:
    if isinstance(target,ast.Name) and target.id in ('MAIN_CODE','INSTALL_CELL'):values[target.id]=ast.literal_eval(node.value)
 code=guard+'\n'+values['MAIN_CODE']
 compile(code,gen,'exec')
 cells=[]
 for source in ([values['INSTALL_CELL']] if values.get('INSTALL_CELL') else [])+[[code]]:
  compile(''.join(source),gen,'exec')
  cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':source})
 notebook={'nbformat':4,'nbformat_minor':4,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'accelerator':'none'},'cells':cells}
 dest=stage/dirname;dest.mkdir(parents=True,exist_ok=True)
 filename=dirname+'.ipynb'
 (dest/filename).write_text(json.dumps(notebook,indent=1),encoding='utf-8')
 metadata=json.loads((ROOT/'fleet/runtime/kaggle_notebooks'/dirname/'kernel-metadata.json').read_text())
 metadata.update({'id':'isearchxsolve/'+slug,'code_file':filename,'enable_gpu':False})
 (dest/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
 print('COMPILE_OK CPU_ONLY',dirname,'cells',len(cells))
