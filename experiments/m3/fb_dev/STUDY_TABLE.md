# FB-dev study (Q112 step 2)

IDs and tags only (FinanceBench text stays in `data/fb_dev/`). Tags: `study_tags.py`; code facts: `study_facts.py`.

**type:** domain 17, metrics 17, novel 16

**answer:** number 21, yes_no 10, choice 6, text 6, absent 4, numbers 3

**calc:** none 23, multi_op 8, one_op 7, rank 6, average 6

**risk:** calc 13, ok 12, quarter 9, search_2pages 6, absent 4, terms 4, judgement 2

**two_pages:** 11 — fb_00215, fb_00711, fb_01107, fb_02024, fb_03473, fb_03856, fb_04254, fb_04481, fb_06247, fb_06741, fb_10136

**constant:** 7 — fb_00711, fb_02608, fb_03473, fb_04302, fb_06247, fb_06741, fb_10136

**terms:** 18 — fb_00215, fb_00552, fb_00711, fb_00799, fb_01319, fb_01930, fb_02119, fb_03029, fb_03882, fb_04254, fb_04302, fb_04481, fb_04700, fb_04854, fb_06247, fb_06741, fb_09724, fb_10136

**quarter:** 12 — fb_00299, fb_00394, fb_00603, fb_00651, fb_00724, fb_00941, fb_01476, fb_01487, fb_01491, fb_01902, fb_01930, fb_02119

**judgement:** 6 — fb_00206, fb_00215, fb_00685, fb_00720, fb_00839, fb_02119

**split_table:** 23 — fb_00517, fb_00521, fb_00552, fb_00585, fb_00711, fb_00720, fb_00799, fb_01319, fb_01351, fb_01487, fb_01930, fb_02608, fb_03029, fb_03471, fb_03473, fb_03856, fb_03882, fb_04481, fb_04854, fb_06247, fb_06741, fb_07661, fb_10136

**untitled_table:** 12 — fb_00215, fb_00299, fb_00394, fb_00552, fb_00711, fb_01476, fb_01964, fb_03856, fb_03882, fb_04254, fb_04854, fb_06247

| ID | Type | Pages | Answer | Calc | Constant | Terms | Quarter | Judgement | Risk |
|---|---|---|---|---|---|---|---|---|---|
| fb_00206 | domain | 1 | absent | none |  |  |  | yes | absent |
| fb_00215 | domain | 2 | yes_no | one_op |  | yes |  | yes | search_2pages |
| fb_00299 | novel | 1 | choice | rank |  |  | yes |  | quarter |
| fb_00394 | novel | 1 | choice | rank |  |  | yes |  | quarter |
| fb_00464 | novel | 1 | yes_no | none |  |  |  |  | ok |
| fb_00517 | domain | 1 | yes_no | multi_op |  |  |  |  | calc |
| fb_00521 | domain | 1 | absent | none |  |  |  |  | absent |
| fb_00552 | domain | 1 | yes_no | multi_op |  | yes |  |  | calc |
| fb_00585 | novel | 1 | numbers | multi_op |  |  |  |  | calc |
| fb_00603 | novel | 1 | text | none |  |  | yes |  | quarter |
| fb_00651 | novel | 1 | yes_no | none |  |  | yes |  | quarter |
| fb_00684 | domain | 1 | yes_no | multi_op |  |  |  |  | calc |
| fb_00685 | domain | 1 | yes_no | multi_op |  |  |  | yes | calc |
| fb_00711 | domain | 2 | number | average | yes | yes |  |  | calc |
| fb_00720 | domain | 1 | absent | none |  |  |  | yes | absent |
| fb_00724 | novel | 1 | choice | rank |  |  | yes |  | quarter |
| fb_00799 | domain | 1 | yes_no | multi_op |  | yes |  |  | calc |
| fb_00839 | novel | 1 | yes_no | none |  |  |  | yes | judgement |
| fb_00941 | domain | 1 | text | none |  |  | yes |  | quarter |
| fb_01077 | domain | 1 | text | none |  |  |  |  | ok |
| fb_01107 | domain | 2 | text | none |  |  |  |  | search_2pages |
| fb_01198 | domain | 1 | text | none |  |  |  |  | ok |
| fb_01275 | domain | 1 | choice | rank |  |  |  |  | ok |
| fb_01319 | domain | 1 | absent | none |  | yes |  |  | absent |
| fb_01351 | domain | 1 | numbers | none |  |  |  |  | ok |
| fb_01476 | novel | 1 | number | none |  |  | yes |  | quarter |
| fb_01487 | novel | 1 | yes_no | none |  |  | yes |  | quarter |
| fb_01491 | novel | 1 | number | none |  |  | yes |  | ok |
| fb_01902 | novel | 1 | choice | rank |  |  | yes |  | quarter |
| fb_01930 | novel | 1 | text | none |  | yes | yes |  | terms |
| fb_01964 | novel | 1 | choice | rank |  |  |  |  | ok |
| fb_02024 | novel | 2 | numbers | none |  |  |  |  | search_2pages |
| fb_02119 | novel | 1 | number | one_op |  | yes | yes | yes | judgement |
| fb_02608 | metrics | 1 | number | average | yes |  |  |  | calc |
| fb_03029 | metrics | 1 | number | none |  | yes |  |  | terms |
| fb_03471 | metrics | 1 | number | one_op |  |  |  |  | ok |
| fb_03473 | metrics | 2 | number | average | yes |  |  |  | calc |
| fb_03856 | metrics | 2 | number | one_op |  |  |  |  | search_2pages |
| fb_03882 | metrics | 1 | number | none |  | yes |  |  | terms |
| fb_04209 | metrics | 1 | number | none |  |  |  |  | ok |
| fb_04254 | metrics | 2 | number | one_op |  | yes |  |  | search_2pages |
| fb_04302 | metrics | 1 | number | average | yes | yes |  |  | calc |
| fb_04481 | metrics | 2 | number | multi_op |  | yes |  |  | search_2pages |
| fb_04700 | metrics | 1 | number | none |  | yes |  |  | terms |
| fb_04854 | metrics | 1 | number | one_op |  | yes |  |  | ok |
| fb_06247 | metrics | 2 | number | average | yes | yes |  |  | calc |
| fb_06741 | metrics | 2 | number | average | yes | yes |  |  | calc |
| fb_07661 | metrics | 1 | number | none |  |  |  |  | ok |
| fb_09724 | metrics | 1 | number | one_op |  | yes |  |  | ok |
| fb_10136 | metrics | 2 | number | multi_op | yes | yes |  |  | calc |
