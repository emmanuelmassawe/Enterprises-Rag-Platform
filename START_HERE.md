# ANZA HAPA: Jinsi ya kumpa Codex mradi huu

Kifurushi hiki kina kila kitu cha kumwezesha Codex kutengeneza RAG ya production kwa hatua, huku wewe ukikagua kila hatua.

## Faili zilizomo

| Faili | Kazi |
|---|---|
| `AGENTS.md` | Kanuni fupi za kudumu. Codex anazisoma kiotomatiki kila kikao. |
| `docs/BRIEF.md` | Maelekezo kamili ya mradi (usalama, Redis, LangSmith, Grafana, UI, production-readiness). |
| `docs/OWNER_DECISIONS.md` | Maswali unayopaswa kujibu **kabla** ya kuanza. |
| `docs/APPROVALS.md` | Orodha ya idhini. **Wewe peke yako** unaweka tiki. |
| `docs/PROMPTS.md` | Prompts za kila hatua (0 hadi 9) na prompts za kusaidia. |
| `.gitignore` | Inazuia secrets na state za Terraform kuingia kwenye git. |

## Hatua ya 1: Maandalizi (mara moja)

1. Tengeneza repo kwenye GitHub (umechagua **public**, tazama sehemu "Repo ya public" hapo chini), kisha weka faili zote za kifurushi hiki kwenye root ya repo na ufanye commit ya kwanza.
2. Jaza `docs/OWNER_DECISIONS.md`. Muhimu zaidi: lugha za documents (kama kuna Kiswahili, embedding lazima iunge lugha nyingi), bajeti, na idadi ya watumiaji. Majibu haya yanabadilisha malengo ya NFR.
3. Tengeneza akaunti na funguo (staging kwanza): Render, LangSmith, Grafana Cloud, S3-compatible bucket (au R2), na funguo za LLM na embeddings. **Usimpe Codex funguo za production.**
4. Weka branch protection kwenye `main`.

### Repo ya public: fanya haya KABLA ya commit ya kwanza

- Washa **Secret scanning** na **Push protection**: Settings, Code security. Washa pia Dependabot na CodeQL.
- Weka branch protection kwenye `main` (PR na ukaguzi vinahitajika).
- Tengeneza **Environments** mbili (`staging`, `production`) kwenye Settings, na uweke "Required reviewers" kwa `production`. Funguo zote ziwekwe kama GitHub Secrets kwenye environments hizi, si kwenye code.
- Settings, Actions: weka "Require approval for all outside collaborators" ili workflows za watu wa nje zisikimbie bila idhini yako.
- Usiweke kamwe kwenye repo: funguo, `.env`, `*.tfvars` zenye thamani, Terraform state, documents halisi za wateja, au data halisi. Data ya majaribio iwe ya kutengeneza (synthetic).
- Funguo ikiingia kwenye repo hata kwa sekunde chache, ichukulie kama imeibiwa: **ibadilishe (rotate) mara moja**. Kuifuta kwenye history hakutoshi.
- Chagua leseni kwa makusudi (mfano Apache-2.0 au MIT ukitaka open source). Repo ya public isiyo na leseni inamaanisha "haki zote zimehifadhiwa".
- Ushauri wangu: kwa kuwa mradi huu utakuwa na maelezo ya miundombinu na usalama, fikiria kuanza kwa **repo private** (GitHub inaruhusu repo private za bure) na kuifanya public baadaye ukipenda. Lakini ukiamua public, hatua hizi zinatosha kuifanya salama kwa kiwango kinachokubalika.

## Hatua ya 2: Kuendesha Codex

Codex inapatikana kama CLI, extension ya IDE, app na toleo la cloud. Nimethibitisha kwenye nyaraka zake rasmi kwamba Codex husoma `AGENTS.md` kutoka root ya repo na kuiunganisha kabla ya kazi kuanza. Mipaka na tabia za bidhaa hubadilika, kwa hiyo angalia nyaraka za sasa.

- **Ushauri:** tumia Codex **ndani ya kompyuta yako (CLI au IDE)** kwa mradi huu. Docker compose, Postgres, Redis na majaribio ya Terraform yanahitaji mazingira halisi. Toleo la cloud lina sandbox yenye mtandao mdogo, na litahitaji maandalizi ya ziada.
- Anzisha kila kikao ndani ya folder ya repo (hii inahakikisha `AGENTS.md` inasomwa). Kikao kipya kwa kila milestone ni bora.
- `AGENTS.md` ina ukomo wa takriban 32 KiB (`project_doc_max_bytes`). Faili hii imewekwa fupi kwa makusudi, na maelezo marefu yako kwenye `docs/BRIEF.md`.
- Chagua modeli yenye uwezo mkubwa zaidi na reasoning ya juu kwa Milestone 0, 2 (RLS) na 5 (usalama). Kwa kazi nyepesi unaweza kupunguza.
- Mruhusu Codex aendeshe amri ndani ya repo, lakini angalia kila ombi la ruhusa. Usimruhusu kuendesha `terraform apply` kwenye production.

## Hatua ya 3: Mzunguko wa kila milestone

1. Fungua `docs/PROMPTS.md`, nakili **Prompt 0**, na umpe Codex.
2. Subiri amalize. Atakupa muhtasari na maswali.
3. **Kagua kwa makini.** Soma nyaraka alizozitengeneza, jibu maswali yake kwenye `docs/APPROVALS.md` (sehemu ya Owner notes), na usiweke tiki kabla hujaridhika.
4. Tumia "Review a milestone" kutoka sehemu ya utility prompts kwenye kikao kipya kama ukaguzi huru wa pili.
5. Ukiridhika, weka tiki kwenye `docs/APPROVALS.md`, kisha nakili prompt inayofuata.
6. Rudia hadi Milestone 9.

## Mambo ya kukagua kabla ya kuweka tiki

- **Milestone 0:** je, kila requirement ina kigezo cha kukubalika? Je, NFR zina namba halisi unazoziweza kuzikubali (gharama, latency, availability)?
- **Milestone 2:** je, jaribio la cross-tenant (RLS) lipo na linapita?
- **Milestone 3 na 4:** jaribu mwenyewe kupakia document yenye maagizo yaliyofichwa na uone kama mfumo unayakataa.
- **Milestone 5:** soma ripoti ya red-team (Attack Success Rate) na uulize kuhusu kila kategoria isiyofikia kikomo.
- **Milestone 7:** soma `terraform plan` yote kabla ya kuruhusu apply yoyote. Apply ya production ifanywe na pipeline pekee, baada ya idhini yako.
- **Milestone 9:** hakikisha kila kipengele cha PRODUCTION_READINESS kina **ushahidi**, si madai tu.

## Ukweli wa kuzingatia

- Kifurushi hiki kinaboresha sana nafasi ya kupata mradi bora, lakini hakihakikishi matokeo. Codex anaweza kukosea au kudai kitu kimefanya kazi bila kukijaribu. Ndiyo sababu kila hatua ina ukaguzi wako na ushahidi wa amri zilizoendeshwa.
- Mradi huu ni mkubwa. Tarajia vikao vingi na marekebisho kadhaa kwa kila milestone.
- Gharama zitakuwepo: plans za Render za kulipia (Postgres, Key Value x2, services), LangSmith, Grafana Cloud, na matumizi ya LLM. Angalia bei halisi kabla ya kuwasha production.
- Kabla ya kutumia data halisi za wateja, pata ushauri wa kisheria kuhusu ulinzi wa data unaohusika.
