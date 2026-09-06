"""Validate executable structure and report legitimate many-to-many mappings."""
from collections import defaultdict
import unicodedata

def validate_rules(rules,confirmed):
    for key in ['consonants','vowels','tones','special_consonant_rules','special_symbols']:
        if not isinstance(rules.get(key),dict):raise ValueError('Invalid group_rules section: '+key)
    uses=defaultdict(list);aliases=defaultdict(list)
    for name,rule in rules['consonants'].items():
        readings=rule.get('ipa');readings=readings if isinstance(readings,list) else [readings]
        if not readings or not all(isinstance(x,str) and x for x in readings):raise ValueError('Invalid consonant aliases: '+name)
        for cls in ('low','high'):
            char=rule.get(cls)
            if not isinstance(char,str) or len(char)!=1:raise ValueError('Invalid consonant character: '+name)
            uses[char].append('consonants.'+name+'.'+cls)
        for alias in readings:aliases[alias.lower()].append(name)
    for pos,entries in rules['vowels'].items():
        for pattern,rule in entries.items():
            if not rule.get('ipa'):raise ValueError('Missing vowel reading: '+pattern)
            for c in pattern.replace('...',''):uses[c].append('vowels.'+pos)
    for cls in ('low','high'):
        if set(confirmed['tone_rules'][cls])!={'none','꪿','꫁'}:raise ValueError('Incomplete confirmed tone table')
    for rule in confirmed['special_rime_rules'].values():
        if rule['status'] not in ('confirmed','inferred','experimental'):raise ValueError('Invalid rime rule status')
    return {'overlapping_characters':{c:refs for c,refs in uses.items() if len(refs)>1},
            'ambiguous_alias_groups':{a:g for a,g in aliases.items() if len(g)>1},
            'unassigned_codepoints':[{'character':c,'codepoint':f'U+{ord(c):04X}'} for c in uses if unicodedata.name(c,None) is None]}
