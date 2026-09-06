"""Conservative, provenance-aware Tai Viet engine. Original source rules are read only.

`ipa` in the source means candidate Vietnamese spellings, not international IPA.
Unsupported patterns return diagnostics. No tokenizer or dictionary lookup is used
to pretend that a rule generated an answer.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict, Counter
from functools import lru_cache
import hashlib
import itertools
import json
import re
import unicodedata as ud
from copy import deepcopy
from .validator import validate_rules

ROOT = Path(__file__).resolve().parents[1]
TONE_MARKS = {'\u0300': 'huyền', '\u0301': 'sắc', '\u0309': 'hỏi',
              '\u0303': 'ngã', '\u0323': 'nặng', '\u0304': 'macron'}
TONE_ACCENTS = {v: k for k, v in TONE_MARKS.items()}


def values(value):
    return value if isinstance(value, list) else [value]


def tokenize_sentence(text):
    """Offsets are Python Unicode codepoint offsets; all separators are lossless."""
    result=[]
    for index,char in enumerate(text):
        kind=('whitespace' if char.isspace() else 'special' if '\uaadb'<=char<='\uaadf'
              else 'punctuation' if ud.category(char)[0] in ('P','S') else 'word')
        if result and result[-1]['kind']==kind and kind in ('word','whitespace'):
            result[-1]['text']+=char;result[-1]['end']=index+1
        else:result.append(dict(kind=kind,text=char,start=index,end=index+1))
    return result


def remove_tone(text):
    tones = [TONE_MARKS[c] for c in ud.normalize('NFD', text) if c in TONE_MARKS]
    base = ud.normalize('NFC', ''.join(c for c in ud.normalize('NFD', text) if c not in TONE_MARKS))
    return base, (tones[0] if len(tones) == 1 else 'ngang' if not tones else 'unsupported_multiple_tones')


def spell_tone(initial, vowel, final, tone, vowel_index=None):
    """Orthographic tone placement in the Vietnamese-style nucleus; never Tai mutation."""
    if tone is None:
        return None
    if tone == 'ngang':
        return initial + vowel + (final or '')
    accent = TONE_ACCENTS.get(tone)
    if not accent:
        return None
    positions = [i for i, c in enumerate(vowel) if c in 'aăâeêioôơuưy']
    if not positions:
        return None
    preferred = [i for i in positions if vowel[i] in 'êơ']
    pos = vowel_index if vowel_index is not None else preferred[-1] if preferred else positions[0]
    return ud.normalize('NFC', initial + vowel[:pos] + vowel[pos] + accent + vowel[pos+1:] + (final or ''))


@dataclass
class SyllableAnalysis:
    initial: str
    initial_group: str
    initial_class: str
    vowel: str
    final: str | None
    tone: str | None
    tone_mark: str | None
    syllable_type: str
    matched_rules: list
    ambiguities: list
    vowel_rule: str = ''
    tone_position: int | None = None
    components: list | None = None
    confidence: float | None = None
    medial: str | None = None
    syllable_pattern: str = 'general'


class Engine:
    def __init__(self, rules_path=None, dictionary_path=None):
        path = Path(rules_path or ROOT / 'scripts/group_rules.py')
        raw = path.read_bytes()
        confirmed_raw=(ROOT/'tai_engine/confirmed_rules.json').read_bytes()
        self.confirmed=json.loads(confirmed_raw)
        self.version=self.confirmed['version']+':'+hashlib.sha256(raw+confirmed_raw).hexdigest()
        self.tone_rules=self.confirmed['tone_rules']
        self.special_rimes={k:v for k,v in self.confirmed['special_rime_rules'].items() if v['status']=='confirmed'}
        self.rules = json.loads(raw.decode('utf-8-sig'))
        self.rule_diagnostics=validate_rules(self.rules,self.confirmed)
        self.consonants, self.reverse_consonants = {}, defaultdict(list)
        for group, item in self.rules['consonants'].items():
            for cls in ('low', 'high'):
                char = item[cls]
                self.consonants[char] = dict(group=group, cls=cls, readings=values(item['ipa']))
                for roman in values(item['ipa']):
                    self.reverse_consonants[roman.lower()].append(char)
        carrier=self.confirmed.get('zero_initial',{})
        if carrier.get('status')=='confirmed':
            for cls in ('low','high'):
                char=self.rules['consonants'][carrier['group']][cls]
                self.consonants[char]['readings']=[*self.consonants[char]['readings'],'']
                self.reverse_consonants[''].append(char)
        self.vowels, self.reverse_vowels = {}, defaultdict(list)
        self.disabled_vowel_rules={}
        for pos, entries in self.rules['vowels'].items():
            for pattern, item in entries.items():
                rid = f'vowels.{pos}.{pattern}'
                self.vowels[rid] = dict(pos=pos, pattern=pattern, readings=values(item['ipa']), **{'name': item['name']})
                chars=pattern.replace('...','')
                if any(not ('\uaa80'<=c<='\uaadf') or ud.name(c,None) is None for c in chars):
                    self.disabled_vowel_rules[rid]='Non-Tai or unassigned grapheme; needs confirmation'
                    continue
                for roman in values(item['ipa']):
                    self.reverse_vowels[roman].append(rid)
        for pos,entries in self.confirmed.get('vowel_additions',{}).items():
            for pattern,item in entries.items():
                if item['status']!='confirmed':continue
                rid=f'confirmed_vowels.{pos}.{pattern}'
                self.vowels[rid]=dict(pos=pos,pattern=pattern,readings=values(item['ipa']),name=item['name'])
                for roman in values(item['ipa']):self.reverse_vowels[roman].append(rid)
        self.tones = self.rules['tones']
        # Explicit prose adapters: references point to the unmodified source.
        self.special_finals = {}
        adapters = {'phu_am_J': ['i'], 'phu_am_V': ['o', 'u'], 'phu_am_B': ['p'], 'phu_am_D': ['t']}
        for name, readings in adapters.items():
            if name in self.rules['special_consonant_rules']:
                char = self.rules['special_consonant_rules'][name]['character']
                self.special_finals[char] = (readings, 'special_consonant_rules.' + name)
        # Ordinary sonorant codas are listed in taiviet_rules.VALID_FINALS;
        # character/class mappings still come exclusively from group_rules.
        self.final_readings=dict(self.special_finals)
        for c,meta in self.consonants.items():
            readings=[r for r in meta['readings'] if r in ('m','n','ng')]
            if readings and meta['cls']=='high':self.final_readings[c]=(readings,'ordinary_final:'+meta['group'])
        self.alias_groups=defaultdict(set)
        for group,item in self.rules['consonants'].items():
            for alias in values(item['ipa']):self.alias_groups[alias.lower()].add(group)
        if carrier.get('status')=='confirmed':self.alias_groups[''].add(carrier['group'])
        self.words, self.romans = defaultdict(list), defaultdict(list)
        self.layouts = defaultdict(Counter)
        path = Path(dictionary_path or ROOT / 'data/taiviet_dictionary_dataset.json')
        self.records = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else []
        for row in self.records:
            word, roman = row.get('tu_thai'), row.get('phien_am')
            if not isinstance(word, str) or not isinstance(roman, str):
                continue
            self.words[word].append(roman)
            self.romans[roman].append(word)
        self.canonical_dictionary=defaultdict(list)
        for roman,words in self.romans.items():
            for key in self.canonical_keys(roman):
                self.canonical_dictionary[key].extend(words)
        # Layout evidence is structural corpus evidence, NOT a confirmed tone rule.
        for word in self.words:
            for syllable in word.split():
                for a in self.parse_syllable(syllable):
                    if a['tone_mark']:
                        self.layouts[(a['vowel_rule'], bool(a['final']))][a['tone_position']] += 1

    def resolve_tone(self, cls, mark, final):
        if final in self.special_finals and self.special_finals[final][0] in (['p'], ['t']):
            if mark: return None
            return 'sắc' if cls == 'low' else 'nặng'
        return self.tone_rules.get(cls,{}).get(mark or 'none')

    def tone_to_marks(self,cls,tone):
        return [None if mark=='none' else mark for mark,t in self.tone_rules.get(cls,{}).items() if t==tone]

    def canonical_keys(self,text):
        """Alias-aware search representation only; never rewrites original data.

        The rime retains every base letter and tone; group identifiers are derived
        from each alias array, including an alias belonging to multiple groups.
        """
        groups=[]
        for token in tokenize_sentence(text):
            if token['kind']!='word':
                if token['kind']=='whitespace':continue
                groups.append([token['text']]);continue
            base,tone=remove_tone(ud.normalize('NFC',token['text']).lower())
            initials=[a for a in self.alias_groups if base.startswith(a) and len(base)>len(a)]
            if not initials:groups.append([f'raw:{base}|{tone}']);continue
            size=max(map(len,initials));initials=[a for a in initials if len(a)==size]
            groups.append([f'{g}|{base[len(a):]}|{tone}' for a in initials for g in sorted(self.alias_groups[a])])
        return [' '.join(x) for x in itertools.islice(itertools.product(*groups),256)] if groups else []

    def dictionary_tai_candidates(self,text):
        found=list(self.romans.get(text,[]))
        for key in self.canonical_keys(text):found.extend(self.canonical_dictionary.get(key,[]))
        return list(dict.fromkeys(found))

    def aliases_equivalent(self,left,right):
        return bool(set(self.canonical_keys(left)) & set(self.canonical_keys(right)))

    def base_compose(self, initial, rid, final=None):
        if rid.startswith('special:'):
            return initial+self.special_rimes[rid[8:]]['tai_tail']
        vowel = self.vowels[rid]
        p, pos = vowel['pattern'], vowel['pos']
        if pos == 'pos_wrap':
            left, right = p.split('...')
            return left + initial + right + (final or '')
        if pos == 'pos_left': return p + initial + (final or '')
        return initial + p + (final or '')

    def parse_syllable(self, word):
        # Callers may edit a selected analysis; never expose mutable cached objects.
        return deepcopy(self._parse_syllable(word))

    @lru_cache(maxsize=40000)
    def _parse_syllable(self, word):
        marks = [(i, c) for i, c in enumerate(word) if c in self.tones]
        if len(marks) > 1: return []
        mark = marks[0][1] if marks else None
        tone_pos = marks[0][0] if marks else None
        base = ''.join(c for c in word if c not in self.tones)
        result = []
        for name,rule in self.special_rimes.items():
            if len(base)!=1+len(rule['tai_tail']) or base[1:]!=rule['tai_tail'] or base[0] not in self.consonants:continue
            if mark and not 1<=tone_pos<=len(base):continue
            c=self.consonants[base[0]]
            a=SyllableAnalysis(base[0],c['group'],c['cls'],rule['vowel'],rule['final_character'],
                self.resolve_tone(c['cls'],mark,rule['final_character']),mark,'closed',
                ['special_rime_rules.'+name,'tone_rules.'+c['cls']+'.'+(mark or 'none')],[],
                'special:'+name,tone_pos,medial=rule['medial'],syllable_pattern=name)
            result.append(asdict(a))
        if result:return result
        for rid, vowel in self.vowels.items():
            if rid in self.disabled_vowel_rules:continue
            # Modifier and special constrained vowel require more context than provided.
            if vowel['pos'] == 'pos_modifier' or vowel['pattern'] == 'ꪽ': continue
            p, pos = vowel['pattern'], vowel['pos']
            if pos == 'pos_wrap':
                left, right = p.split('...')
                if not base.startswith(left): continue
                rem = base[len(left):]
                if len(rem) < 1 or not rem[1:].startswith(right): continue
                initial, final = rem[0], rem[1+len(right):]
            elif pos == 'pos_left':
                if not base.startswith(p): continue
                rem = base[len(p):]
                if not rem: continue
                initial, final = rem[0], rem[1:]
            else:
                if not base or not base[1:].startswith(p): continue
                initial, final = base[0], base[1+len(p):]
            if initial not in self.consonants or (final and final not in self.consonants): continue
            if pos == 'pos_middle' and not final: continue
            if mark and not (base.index(initial) + 1 <= tone_pos <= len(base) - len(final)): continue
            c = self.consonants[initial]
            ambiguity = []
            if vowel['pattern'] == 'ꪾ': ambiguity.append('U+AABE appears as ê and ăm in group_rules')
            if final and final not in self.final_readings: ambiguity.append('final pronunciation context not confirmed')
            tone = self.resolve_tone(c['cls'], mark, final)
            if tone is None: ambiguity.append('unmarked tone unresolved; statistical inference disabled')
            rules = [f"consonants.{c['group']}.{c['cls']}", rid,'tone_rules.'+c['cls']+'.'+(mark or 'none')]
            if mark: rules.append('tones.' + mark)
            if final in self.special_finals: rules.append(self.special_finals[final][1])
            a = SyllableAnalysis(initial, c['group'], c['cls'], '/'.join(vowel['readings']),
                final or None, tone, mark, 'closed' if final else 'open', rules, ambiguity,
                rid, tone_pos, [{'role':'initial','text':initial}, {'role':'vowel','pattern':p},
                               {'role':'final','text':final or None}, {'role':'tone','text':mark}])
            result.append(asdict(a))
        # Compound vowel patterns take precedence over smaller decompositions.
        wraps = [a for a in result if self.vowels[a['vowel_rule']]['pos'] == 'pos_wrap']
        return wraps or result

    def parse_tai_word(self, word):
        if not isinstance(word, str): raise ValueError('Tai input must be a string')
        parts = re.split(r'(\s+)', word)
        syllables = [{'original': p, 'candidates': self.parse_syllable(p)} for p in parts if p and not p.isspace()]
        supported = bool(syllables) and all(s['candidates'] for s in syllables)
        return dict(original=word, rule_version=self.version, supported=supported,
                    parts=parts, syllables=syllables,
                    diagnostics=[] if supported else ['unsupported syllable structure; original preserved'])

    def compose_syllable(self, analysis):
        a = asdict(analysis) if isinstance(analysis, SyllableAnalysis) else analysis
        if a['initial'] not in self.consonants or (a['vowel_rule'] not in self.vowels and a['vowel_rule'] not in ['special:'+n for n in self.special_rimes]):
            raise ValueError('Unknown component rule')
        if a.get('final') and a['final'] not in self.consonants: raise ValueError('Unknown final')
        result = self.base_compose(a['initial'], a['vowel_rule'], a.get('final'))
        if a.get('tone_mark'):
            if a['tone_mark'] not in self.tones: raise ValueError('Unknown tone mark')
            index = a.get('tone_position')
            if not isinstance(index, int) or not 0 <= index <= len(result): raise ValueError('Tone layout unavailable')
            result = result[:index] + a['tone_mark'] + result[index:]
        if not any(x['initial'] == a['initial'] and x['vowel_rule'] == a['vowel_rule'] and
                   x['final'] == a.get('final') for x in self.parse_syllable(result)):
            raise ValueError('Unsupported composition')
        return result

    def compose_tai_word(self, parsed):
        if 'syllables' not in parsed: return self.compose_syllable(parsed)
        if not parsed['supported']: raise ValueError('Cannot compose unsupported analysis')
        output, index = [], 0
        for part in parsed['parts']:
            if not part or part.isspace(): output.append(part); continue
            candidates = {self.compose_syllable(a) for a in parsed['syllables'][index]['candidates']}
            if len(candidates) != 1: raise ValueError('Ambiguous spelling; select an analysis')
            output.append(next(iter(candidates))); index += 1
        return ''.join(output)

    def parse_romanization(self, text):
        base, tone = remove_tone(text.lower())
        candidates = []
        for initial in sorted(self.reverse_consonants, key=len, reverse=True):
            if not base.startswith(initial): continue
            rest = base[len(initial):]
            for name,rule in self.special_rimes.items():
                if rest==rule['romanization_rime']:
                    candidates.append(asdict(SyllableAnalysis(initial,','.join(sorted(self.alias_groups[initial])), '',
                        rule['vowel'],rule['final'],tone,None,'closed',['special_rime_rules.'+name],[],
                        'special:'+name,medial=rule['medial'],syllable_pattern=name)))
            for vowel in sorted(self.reverse_vowels, key=len, reverse=True):
                if not rest.startswith(vowel): continue
                final = rest[len(vowel):]
                allowed = {r for readings, _ in self.final_readings.values() for r in readings}
                if final and final not in allowed: continue
                candidates.append(asdict(SyllableAnalysis(initial, ','.join(sorted(self.alias_groups[initial])), '', vowel, final or None,
                    tone, None, 'closed' if final else 'open', self.reverse_vowels[vowel], [],
                    self.reverse_vowels[vowel][0])))
        if candidates:
            longest_initial = max(len(a['initial']) for a in candidates)
            candidates = [a for a in candidates if len(a['initial']) == longest_initial]
            special=[a for a in candidates if a['vowel_rule'].startswith('special:')]
            if special:return {'input':text,'candidates':special,'rule_version':self.version}
            longest_vowel = max(len(a['vowel']) for a in candidates)
            candidates = [a for a in candidates if len(a['vowel']) == longest_vowel]
        return {'input':text, 'candidates':candidates, 'rule_version':self.version}

    def _roman_syllable(self, word):
        results = []
        for a in self.parse_syllable(word):
            if a['tone'] is None: continue
            if a['vowel_rule'].startswith('special:'):
                rule=self.special_rimes[a['syllable_pattern']]
                for initial in self.consonants[a['initial']]['readings']:
                    text=spell_tone(initial,rule['vowel'],rule['final'],a['tone'],rule['tone_vowel_index'])
                    results.append(dict(romanization=text,analysis=a,source='rule_based',confidence=None))
                continue
            finals = [None]
            if a['final']:
                if a['final'] not in self.final_readings: continue
                finals = self.final_readings[a['final']][0]
            for initial, vowel, final in itertools.product(self.consonants[a['initial']]['readings'],
                    self.vowels[a['vowel_rule']]['readings'], finals):
                text = spell_tone(initial, vowel, final, a['tone'])
                if text: results.append(dict(romanization=text, analysis=a, source='rule_based', confidence=None))
        return results

    def tai_to_romanization(self, word, dictionary=False, limit=100):
        tokens=tokenize_sentence(word)
        if len(tokens)!=1 or (tokens and tokens[0]['kind']!='word'):
            return self.tai_sentence_to_romanization(word,dictionary=dictionary,limit=limit)
        parts = word.split()
        groups = [self._roman_syllable(p) for p in parts]
        generated = []
        if groups and all(groups):
            for combo in itertools.islice(itertools.product(*groups), limit + 1):
                generated.append(dict(romanization=' '.join(x['romanization'] for x in combo),
                    source='rule_based', confidence=None, analyses=[x['analysis'] for x in combo]))
        unique = {x['romanization']: x for x in generated}
        items = sorted(unique.values(), key=lambda x: (-self.words.get(word,[]).count(x['romanization']), x['romanization']))
        result = dict(input=word, candidates=items[:limit], truncated=len(generated)>limit,
                      rule_version=self.version, ranking='dictionary_frequency_then_lexical_not_probability')
        if dictionary:
            result['dictionary_candidates'] = [dict(romanization=r, source='dictionary_lookup') for r in dict.fromkeys(self.words.get(word,[]))]
        return result

    def _tai_syllable(self, text):
        results = []
        for ra in self.parse_romanization(text)['candidates']:
            if ra['vowel_rule'].startswith('special:'):
                rule=self.special_rimes[ra['syllable_pattern']]
                for initial in self.reverse_consonants[ra['initial']]:
                    for mark in self.tone_to_marks(self.consonants[initial]['cls'],ra['tone']):
                        # The confirmed examples contain no tone mark. Marked variants
                        # require observed layout evidence for this rime, not a guessed slot.
                        positions=list(self.layouts.get((ra['vowel_rule'],True),{})) if mark else [None]
                        for position in positions:
                            a=dict(initial=initial,vowel_rule=ra['vowel_rule'],final=rule['final_character'],
                                tone_mark=mark,tone_position=position)
                            word=self.compose_syllable(a)
                            results.append(dict(tai=word,analysis=a,source='rule_based',
                                layout_source='observed_corpus_layout' if mark else 'confirmed_pattern',confidence=None))
                continue
            finals = [None] if not ra['final'] else [c for c, (rs, _) in self.final_readings.items() if ra['final'] in rs]
            for initial, rid, final in itertools.product(self.reverse_consonants[ra['initial']],
                    self.reverse_vowels[ra['vowel']], finals):
                cls = self.consonants[initial]['cls']
                for mark in [None, *self.tones]:
                    if self.resolve_tone(cls, mark, final) != ra['tone']: continue
                    # Promt3 explicitly confirms a post-vowel tone layout for ordinary
                    # a syllables; other layouts retain their observed provenance.
                    layouts = list(self.layouts[(rid, bool(final))]) if mark else [None]
                    if mark and self.vowels[rid]['pattern']=='ꪱ':layouts=list(dict.fromkeys([len(self.base_compose(initial,rid,final))-len(final or ''),*layouts]))
                    for position in layouts:
                        a = dict(initial=initial, vowel_rule=rid, final=final, tone_mark=mark, tone_position=position)
                        try: word = self.compose_syllable(a)
                        except ValueError: continue
                        results.append(dict(tai=word, analysis=a, source='rule_based',
                            layout_source='observed_corpus_layout' if mark else 'group_rules', confidence=None))
        return results

    def romanization_to_tai(self, text, dictionary=False, limit=100):
        tokens=tokenize_sentence(text)
        if len(tokens)!=1 or (tokens and tokens[0]['kind']!='word'):
            return self.romanization_sentence_to_tai(text,dictionary=dictionary,limit=limit)
        groups = [self._tai_syllable(p) for p in text.split()]
        generated = []
        if groups and all(groups):
            for combo in itertools.islice(itertools.product(*groups), limit + 1):
                generated.append(dict(tai=' '.join(x['tai'] for x in combo), source='rule_based',
                    confidence=None, analyses=list(combo)))
        items = list({x['tai']:x for x in generated}.values())
        matches=self.dictionary_tai_candidates(text)
        items.sort(key=lambda x: (x['tai'] not in matches,-self.romans.get(text,[]).count(x['tai']), x['tai']))
        result = dict(input=text, candidates=items[:limit], truncated=len(generated)>limit,
                      rule_version=self.version, ranking='dictionary_frequency_then_lexical_not_probability')
        if dictionary:
            result['dictionary_candidates'] = [dict(tai=w, source='dictionary_lookup') for w in self.dictionary_tai_candidates(text)]
        return result

    def sentence_convert(self,text,direction,dictionary=False,limit=100):
        field='romanization' if direction=='tai' else 'tai'
        convert=self.tai_to_romanization if direction=='tai' else self.romanization_to_tai
        tokens=tokenize_sentence(text);groups=[];assisted=[];unknown=[];ambiguous=[]
        for i,token in enumerate(tokens):
            if token['kind']!='word':
                fixed={field:token['text'],'source':'preserved_separator'}
                groups.append([fixed]);assisted.append([fixed]);continue
            converted=convert(token['text'],dictionary=dictionary,limit=limit)
            token['candidates']=converted['candidates']
            token['dictionary_candidates']=converted.get('dictionary_candidates',[])
            token['rule_version']=self.version
            groups.append(token['candidates'])
            merged={c[field]:c for c in token['dictionary_candidates']}
            for c in token['candidates']:merged.setdefault(c[field],c)
            assisted.append(list(merged.values()))
            if not merged:unknown.append(i)
            if len(merged)>1:ambiguous.append(i)
        def combine(parts,source):
            if not parts or not all(parts):return [],False
            count=1
            for part in parts:count*=len(part)
            choices=[dict(**{field:''.join(c[field] for c in combo)},source=source,confidence=None,
                          token_sources=[c['source'] for c in combo])
                     for combo in itertools.islice(itertools.product(*parts),limit)]
            return choices,count>limit
        generated,truncated=combine(groups,'rule_based')
        result=dict(input=text,candidates=generated,tokens=tokens,unknown_tokens=unknown,ambiguous_tokens=ambiguous,
                    rule_version=self.version,truncated=truncated,ranking='per_token_dictionary_ranking_then_bounded_product')
        if dictionary:
            extra,cut=combine(assisted,'dictionary_assisted')
            result['dictionary_candidates']=extra
            result['truncated']=truncated or cut
        return result

    def tai_sentence_to_romanization(self,text,**kwargs):return self.sentence_convert(text,'tai',**kwargs)
    def romanization_sentence_to_tai(self,text,**kwargs):return self.sentence_convert(text,'roman',**kwargs)


@lru_cache(maxsize=1)
def default_engine(): return Engine()
def parse_tai_word(word): return default_engine().parse_tai_word(word)
def compose_tai_word(components): return default_engine().compose_tai_word(components)
def parse_romanization(text): return default_engine().parse_romanization(text)
def tai_to_romanization(word, **kwargs): return default_engine().tai_to_romanization(word, **kwargs)
def romanization_to_tai(text, **kwargs): return default_engine().romanization_to_tai(text, **kwargs)
def tai_sentence_to_romanization(text, **kwargs):return default_engine().tai_sentence_to_romanization(text,**kwargs)
def romanization_sentence_to_tai(text, **kwargs):return default_engine().romanization_sentence_to_tai(text,**kwargs)
