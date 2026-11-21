# Self-check for integrity.py: python3 integrity_check.py
import importlib.util
spec = importlib.util.spec_from_file_location('ig', __file__.replace('integrity_check.py', 'integrity.py')); ig = importlib.util.module_from_spec(spec); spec.loader.exec_module(ig)
src = ['Він прийшов додому пізно ввечері і довго сидів біля вікна, дивлячись на темну вулицю внизу.'] * 4 + ['*Курсив* тут.']
ok = {str(i): 'He came home late in the evening and sat by the window for a long time, looking at the dark street below.' for i in range(4)}; ok['4'] = '*Italics* here.'
assert ig.check(src, ok, 'en') == ([], [])
bad = dict(ok); bad['1'] = ''; bad['2'] = 'He came home late, сидів біля вікна довго.'; bad['4'] = 'Italics here.'
inc, warn = ig.check(src, bad, 'en')
assert {k for _, k, _ in inc} == {'empty', 'script'} and {k for _, k, _ in warn} == {'italics', 'length'}, (inc, warn)
uk = {str(i): 'Він прийшов додому пізно ввечері і довго сидів біля вікна, дивлячись на темну вулицю.' for i in range(5)}
uk['3'] = 'Він прийшов «ma petite chère» додому пізно і довго сидів біля вікна.'
assert ig.check(src, uk, 'uk')[0] == []                      # a quoted foreign phrase is fine
uk['3'] = 'Он пришёл домой поздно и сидел у окна, глядя на тёмную улицу.'
assert [k for _, k, _ in ig.check(src, uk, 'uk')[0]] == ['leak']
uk['3'] = 'He came home late and sat by the window for a long time.'
assert [k for _, k, _ in ig.check(src, uk, 'uk')[0]] == ['script']
print('integrity self-check ok')
