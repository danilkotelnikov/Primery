# Fusarium diagnostic loci downloader (NCBI Nucleotide)

Пакет для скачивания последовательностей генов/локусов **Fusarium culmorum** (txid5516) и
**Fusarium graminearum** (txid5518) из **NCBI Nucleotide** с проверкой (QC), что запись действительно
соответствует нужному гену/локусу.

## Что скачивает

Панели (ключ `--panel`):

- `mlst`: TEF1a, RPB2, RPB1, TUB2, CaM/cmdA, HIS3, ACT1  
- `rdna`: ITS, IGS_rDNA, LSU_28S  
- `mito`: FgMito_COB_intron2, FcMito_mtDNA  
- `diagnostic`: FG16_SCAR, CYP51C, IGS_rDNA, FgMito_COB_intron2, FcMito_mtDNA  
- `toxin`: TRI5, TRI12, TRI13, PKS13  
- `all`: все вышеперечисленное

## Файловая структура

Результат сохраняется так:

outdir/
  manifest.tsv
  Fusarium_culmorum/
    TEF1a/
      Fusarium_culmorum__TEF1a__ACCESSION.fasta
    ...
  Fusarium_graminearum/
    ...

## QC / перепроверка гена

Скрипт скачивает GenBank (rettype=gb) и ищет ожидаемые ключевые слова в:
- FEATURES: /gene=, /product=
- DEFINITION

По умолчанию допускается совпадение и в полном тексте GenBank (мягкий режим).
Для жёсткого режима используйте `--strict-qc`.

Если хотите сохранить даже не прошедшие QC записи (с пометкой в manifest.tsv), используйте `--keep-unverified`.

## Установка

```bash
pip install requests
```

## Запуск (пример)

Скачать **по 10 последовательностей на каждый локус** (для обоих видов), и упаковать результат:

```bash
python download_fusarium_loci.py --email you@example.org --panel all --n-per-locus 10 --outdir fusarium_fasta --zip
```

После выполнения:
- FASTA будут в папке `fusarium_fasta/`
- манифест: `fusarium_fasta/manifest.tsv`
- архив: `fusarium_fasta.zip`

### Опционально: NCBI API key
Можно добавить `--api-key <KEY>`, чтобы поднять лимиты запросов NCBI.


---

## BLAST-анализ несовпадений (core_nt) + XLSX

Добавлен скрипт `blast_mismatch_analyzer.py`, который:
- отправляет BLASTN по базе `core_nt`,
- сохраняет JSON2 (ZIP) с BLAST-результатами,
- строит **query-anchored** aligned FASTA (можно открыть/просмотреть в NCBI MSA Viewer как выравнивание),
- суммирует позиции, где **нецелевые виды** чаще всего отличаются от целевой последовательности,
- пишет сводную таблицу в `.xlsx`.

Пример (один локус/файл):

```bash
python blast_mismatch_analyzer.py --email you@example.org \
  --target-sciname "Fusarium culmorum" --target-taxid 5516 \
  --query-fasta fusarium_fasta/Fusarium_culmorum/ITS/Fusarium_culmorum__ITS__ACCESSION.fasta \
  --outdir fusarium_fasta --max-hits 200
```

Пример (все локусы из manifest.tsv; **один query на species×locus**):

```bash
python blast_mismatch_analyzer.py --email you@example.org \
  --outdir fusarium_fasta --analyze-from-manifest --manifest fusarium_fasta/manifest.tsv \
  --target-sciname "Fusarium culmorum" --target-taxid 5516
```

> Для полного набора (и для **двух видов**) удобнее использовать pipeline ниже.

---

## Pipeline: скачать + BLAST-анализ (одной командой)

Скрипт `fusarium_pipeline.py` объединяет скачивание и BLAST-анализ.

### Скачать, затем проанализировать, затем упаковать в zip

```bash
python fusarium_pipeline.py all --email you@example.org --outdir fusarium_fasta \
  --panel all --n-per-locus 10 --max-hits 200 --zip
```

Результат:
- FASTA + manifest: `fusarium_fasta/`
- BLAST-анализ: `fusarium_fasta/blast_analysis/`
- архив: `fusarium_fasta.zip`

---

## Интерактивная версия для произвольного вида

Скрипт `ncbi_loci_interactive.py`:
1) попросит название вида,
2) найдёт taxid в NCBI Taxonomy и попросит подтвердить,
3) покажет топ наиболее "частых" генов/локусов по эвристическим запросам,
4) скачает выбранные локусы (по N штук) в FASTA и соберёт manifest.tsv.

Запуск:

```bash
python ncbi_loci_interactive.py --email you@example.org --outdir out --n-per-locus 10
```



---

## Primer-BLAST: интерактивная проверка специфичности ваших праймеров

Добавлен скрипт `primerblast_interactive.py`, который:
- спрашивает у вас **Forward/Reverse** праймеры (IUPAC DNA),
- спрашивает целевой **вид/подвид**, ищет **taxid** в NCBI Taxonomy и просит подтвердить,
- запускает **NCBI Primer-BLAST** (через веб-форму) и ждёт завершения задания,
- скачивает доступные **табличные выгрузки** (CSV/TSV, если они присутствуют на странице результатов),
- строит отчёт `.xlsx`:
  - `summary`: сколько on-target/off-target ампликонов/видов,
  - `targets`: таблица целей с mismatch-полями (если в выгрузке они присутствуют),
  - `downloads`: какие файлы были скачаны,
  - `meta`: параметры запуска.

Запуск (отдельно):

```bash
python primerblast_interactive.py --email you@example.org --outdir out_primerblast
```

Запуск через общий pipeline:

```bash
python fusarium_pipeline.py primerblast --email you@example.org --outdir out_primerblast
```

По умолчанию база `core_nt` (рекомендована NCBI как более быстрая альтернатива `nt`).  


---

## GUI (SnapGene-like, RU/ENG)

Добавлен `gui_app.py` — графическая оболочка для всего пайплайна:
- левый файловый менеджер (рабочая папка),
- вкладки: Download → Mismatch → Primer3 design → Primer-BLAST → Reports → Viewer,
- бело‑бирюзовая тема, скруглённые кнопки, масштабируемый шрифт,
- переключение языка RU/ENG,
- встроенный HTML-вьюер последовательностей (с треком mismatch% по нецелевым видам).

Запуск:
```bash
python gui_app.py
# или
python fusarium_pipeline.py gui
```


### Интерактивный выбор вида и локусов (NCBI)

1. Вкладка **Скачивание локусов → Организм (NCBI)**.
2. Введите email (NCBI требует), при наличии — API key.
3. Введите запрос (вид/подвид) → **Найти в NCBI**.
4. Выберите подходящий таксон из списка, подтвердите.
5. Нажмите **Список локусов** — отобразятся кандидаты локусов (по NCBI Nucleotide, эвристика по маркерам).
6. Отметьте нужные локусы → **Скачать выбранные**.

После скачивания `manifest.tsv` автоматически подставляется в шаги mismatch/Primer‑BLAST.

### JBrowse2 и визуализация праймеров

Вкладка **Просмотр**:
- **Viewer**: FASTA + (опционально) `mismatch_map.json` + оверлей праймеров из `primer3_pairs.json`.
- **JBrowse2**: embedded Linear Genome View для одного контига + трек праймеров.  
  Примечание: JS‑бандл JBrowse2 загружается с `unpkg.com` (требуется интернет).

### Аппаратное ускорение

GUI включает флаги QtWebEngine/Chromium для использования GPU (если доступно). При необходимости можно переопределить:
- `QT_OPENGL` (`angle`/`desktop`)
- `QTWEBENGINE_CHROMIUM_FLAGS`


### Primer3-дизайн (шаг между mismatch и Primer‑BLAST)
Скрипт `primer3_designer.py`:
- читает `FASTA` + (опционально) mismatch `.xlsx`,
- считает mismatch% по позициям (доля нецелевых видов с несовпадением),
- предлагает топ‑окна (диапазоны) для размещения праймера (с усилением 3′‑конца окна),
- запускает Primer3 (primer3‑py) и добавляет расчёт Tm/hairpin/dimer.

CLI:
```bash
python primer3_designer.py --template-fasta <file.fasta> --mismatch-xlsx <blast.xlsx> --preset qpcr --outdir primer_design
```

### HTML+PDF отчёт
`report_builder.py` собирает репрезентативный отчёт:
```bash
python report_builder.py --workdir <workspace> --outdir <workspace>/report
```

---

## Windows EXE
Проект подготовлен к сборке через PyInstaller (скрипты сборки в пакете).
См. `build_windows.bat` и `pyinstaller.spec`.

