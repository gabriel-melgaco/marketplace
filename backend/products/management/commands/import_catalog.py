import csv
import os

from django.core.management.base import BaseCommand

from products.models import Category, Series, Products


class Command(BaseCommand):
    help = 'Importa categorias, séries e produtos a partir do CSV do catálogo Commander Brasil'

    CSV_PATH = os.path.join('spreadsheets', 'commander_brasil_catalogo_normalizado.csv')

    # URL base de imagens por categoria (coluna Imagem do primeiro produto de cada categoria)
    CATEGORY_IMAGE_URLS: dict[str, str] = {}

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            type=str,
            default=self.CSV_PATH,
            help='Caminho para o arquivo CSV (padrão: spreadsheets/commander_brasil_catalogo_normalizado.csv)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula a importação sem salvar no banco',
        )

    def handle(self, *args, **options):
        csv_path = options['csv']
        dry_run = options['dry_run']

        if not os.path.exists(csv_path):
            self.stderr.write(self.style.ERROR(f'Arquivo não encontrado: {csv_path}'))
            return

        rows = self._read_csv(csv_path)
        self.stdout.write(f'Linhas lidas do CSV: {len(rows)}')

        # Fase 1: Construir URL de imagem por categoria
        self._build_category_image_urls(rows)

        # Fase 2: Criar categorias
        categories = self._create_categories(rows, dry_run)

        # Fase 3: Criar séries
        series = self._create_series(rows, dry_run)

        # Fase 4: Criar produtos
        self._create_products(rows, categories, series, dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — nenhum dado foi salvo.'))
        else:
            self.stdout.write(self.style.SUCCESS('Importação concluída com sucesso!'))

    def _read_csv(self, csv_path):
        rows = []
        with open(csv_path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def _build_category_image_urls(self, rows):
        """Preenche CATEGORY_IMAGE_URLS com a primeira imagem encontrada para cada categoria."""
        for row in rows:
            cat_name = self._normalize_category(row.get('Categoria', ''))
            image_url = (row.get('Imagem') or '').strip()
            if cat_name not in self.CATEGORY_IMAGE_URLS and image_url:
                self.CATEGORY_IMAGE_URLS[cat_name] = image_url

        self.stdout.write(f'URLs de imagem mapeadas para {len(self.CATEGORY_IMAGE_URLS)} categorias')

    def _normalize_category(self, value):
        """Retorna 'Outros' se a categoria estiver vazia ou for '-'."""
        value = (value or '').strip()
        if not value or value == '-':
            return 'Outros'
        return value

    def _normalize_series(self, value):
        """Retorna 'Outros' se a série estiver vazia ou for '-'."""
        value = (value or '').strip()
        if not value or value == '-':
            return 'Outros'
        return value

    def _create_categories(self, rows, dry_run):
        seen = {}
        for row in rows:
            cat_name = self._normalize_category(row.get('Categoria', ''))
            if cat_name in seen:
                continue

            slug = (row.get('slug_categoria') or '').strip()
            if cat_name == 'Outros':
                slug = 'outros'

            if not slug:
                self.stderr.write(self.style.WARNING(f'Categoria sem slug ignorada: {cat_name}'))
                continue

            if dry_run:
                self.stdout.write(f'  [DRY] Categoria: {cat_name} (slug={slug})')
                seen[cat_name] = None
            else:
                obj, created = Category.objects.get_or_create(
                    slug=slug,
                    defaults={'name': cat_name},
                )
                seen[cat_name] = obj
                status = 'criada' if created else 'já existe'
                self.stdout.write(f'  Categoria: {cat_name} ({status})')

        self.stdout.write(f'Total de categorias processadas: {len(seen)}')
        return seen

    def _create_series(self, rows, dry_run):
        seen = {}
        for row in rows:
            serie_name = self._normalize_series(row.get('Serie', ''))
            slug = (row.get('slug_serie') or '').strip()

            if serie_name == 'Outros':
                slug = 'outros'

            if not slug:
                self.stderr.write(self.style.WARNING(f'Série sem slug ignorada: {serie_name}'))
                continue
            if serie_name in seen:
                continue

            if dry_run:
                self.stdout.write(f'  [DRY] Série: {serie_name} (slug={slug})')
                seen[serie_name] = None
            else:
                obj, created = Series.objects.get_or_create(
                    slug=slug,
                    defaults={'name': serie_name},
                )
                seen[serie_name] = obj
                status = 'criada' if created else 'já existe'
                self.stdout.write(f'  Série: {serie_name} ({status})')

        self.stdout.write(f'Total de séries processadas: {len(seen)}')
        return seen

    def _build_slug_counts(self, rows):
        """Conta quantas vezes cada slug_nome aparece no CSV para detectar duplicados."""
        from collections import Counter
        return Counter((row.get('slug_nome') or '').strip() for row in rows)

    def _create_products(self, rows, categories, series, dry_run):
        created_count = 0
        skipped_count = 0
        slug_counts = self._build_slug_counts(rows)
        used_slugs = set()

        for row in rows:
            name = (row.get('Nome') or '').strip()
            code = (row.get('SKU') or '').strip()
            slug = (row.get('slug_nome') or '').strip()
            image_url = (row.get('Imagem') or '').strip()
            cat_name = self._normalize_category(row.get('Categoria', ''))
            serie_name = self._normalize_series(row.get('Serie', ''))

            if not name or not slug:
                self.stderr.write(self.style.WARNING(f'Produto sem nome/slug ignorado: SKU={code}'))
                skipped_count += 1
                continue

            # Diferenciar slug quando houver nomes repetidos
            if slug_counts[slug] > 1:
                slug = f'{slug}-{code.lower()}'

            # Garantir unicidade caso ainda colida
            original_slug = slug
            counter = 2
            while slug in used_slugs:
                slug = f'{original_slug}-{counter}'
                counter += 1
            used_slugs.add(slug)

            category = categories.get(cat_name)
            serie = series.get(serie_name)

            if not dry_run and (category is None or serie is None):
                if category is None:
                    self.stderr.write(self.style.WARNING(
                        f'Categoria não encontrada para produto {name}: "{cat_name}"'
                    ))
                if serie is None:
                    self.stderr.write(self.style.WARNING(
                        f'Série não encontrada para produto {name}: "{serie_name}"'
                    ))
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  [DRY] Produto: {name} (code={code}, slug={slug}, '
                    f'cat={cat_name}, serie={serie_name}, imagem={image_url})'
                )
            else:
                _, created = Products.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'name': name,
                        'code': code,
                        'category': category,
                        'series': serie,
                        'image_url': image_url,
                    },
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

        self.stdout.write(f'Produtos criados: {created_count}, ignorados/existentes: {skipped_count}')
