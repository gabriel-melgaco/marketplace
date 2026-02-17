import csv
import os

from django.core.management.base import BaseCommand

from products.models import Brand


class Command(BaseCommand):
    help = 'Importa marcas a partir do CSV de marcas de equipamentos fitness'

    CSV_PATH = os.path.join('spreadsheets', 'marcas_equipamentos_fitness.csv')

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            type=str,
            default=self.CSV_PATH,
            help='Caminho para o arquivo CSV (padrão: spreadsheets/marcas_equipamentos_fitness.csv)',
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

        rows = []
        with open(csv_path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        self.stdout.write(f'Linhas lidas do CSV: {len(rows)}')

        created_count = 0
        skipped_count = 0

        for row in rows:
            name = (row.get('name') or '').strip()
            slug = (row.get('slug') or '').strip()
            logo = (row.get('logo') or '').strip()
            website = (row.get('website') or '').strip()

            if not name or not slug:
                self.stderr.write(self.style.WARNING(f'Marca sem nome/slug ignorada: {row}'))
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  [DRY] Marca: {name} (slug={slug}, logo={logo}, website={website})'
                )
            else:
                _, created = Brand.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'name': name,
                        'logo': logo,
                        'website': website,
                    },
                )
                status = 'criada' if created else 'já existe'
                self.stdout.write(f'  Marca: {name} ({status})')
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

        self.stdout.write(f'Marcas criadas: {created_count}, ignoradas/existentes: {skipped_count}')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — nenhum dado foi salvo.'))
        else:
            self.stdout.write(self.style.SUCCESS('Importação concluída com sucesso!'))
