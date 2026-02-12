"""
Servico de validacao de regras de transportadoras.

Valida dimensoes e peso de pacotes contra as regras configuradas
por transportadora/modalidade. Usado para filtrar cotacoes retornadas
pelo Melhor Envio e bloquear transportadoras incompativeis ANTES
do comprador prosseguir.
"""

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction

from ..models import CarrierRule

logger = logging.getLogger(__name__)


class CarrierRuleValidationError(Exception):
    """Erro quando nenhuma transportadora e compativel com o pacote."""
    pass


class CarrierRuleService:
    """
    Valida pacotes contra regras de transportadoras configuradas no banco.

    Uso principal:
    - Apos calcular frete no Melhor Envio, filtrar servicos incompativeis
    - Retornar motivos claros de rejeicao para o frontend exibir ao usuario
    """

    @staticmethod
    def validate_package(
        height: Decimal,
        width: Decimal,
        length: Decimal,
        weight: Decimal,
    ) -> dict:
        """
        Valida um pacote contra todas as regras de transportadoras ativas.

        Args:
            height: Altura do pacote em cm
            width: Largura do pacote em cm
            length: Comprimento do pacote em cm
            weight: Peso do pacote em kg

        Returns:
            dict com:
                - eligible: lista de regras compativeis
                - ineligible: lista de dicts com regra e motivos de rejeicao
                - warnings: lista de avisos (ex: taxa de nao mecanizavel)
                - package_info: resumo do pacote validado
        """
        height = Decimal(str(height))
        width = Decimal(str(width))
        length = Decimal(str(length))
        weight = Decimal(str(weight))

        sum_dimensions = height + width + length
        max_side = max(height, width, length)

        rules = CarrierRule.objects.filter(is_active=True)

        eligible = []
        ineligible = []
        warnings = []

        for rule in rules:
            rejection_reasons = []

            # --- Dimensoes minimas ---
            if rule.min_height is not None and height < rule.min_height:
                rejection_reasons.append(
                    f'Altura {height}cm abaixo do minimo {rule.min_height}cm'
                )
            if rule.min_width is not None and width < rule.min_width:
                rejection_reasons.append(
                    f'Largura {width}cm abaixo do minimo {rule.min_width}cm'
                )
            if rule.min_length is not None and length < rule.min_length:
                rejection_reasons.append(
                    f'Comprimento {length}cm abaixo do minimo {rule.min_length}cm'
                )

            # --- Dimensoes maximas ---
            if rule.max_height is not None and height > rule.max_height:
                rejection_reasons.append(
                    f'Altura {height}cm acima do maximo {rule.max_height}cm'
                )
            if rule.max_width is not None and width > rule.max_width:
                rejection_reasons.append(
                    f'Largura {width}cm acima do maximo {rule.max_width}cm'
                )
            if rule.max_length is not None and length > rule.max_length:
                rejection_reasons.append(
                    f'Comprimento {length}cm acima do maximo {rule.max_length}cm'
                )

            # --- Peso ---
            if rule.min_weight is not None and weight < rule.min_weight:
                rejection_reasons.append(
                    f'Peso {weight}kg abaixo do minimo {rule.min_weight}kg'
                )
            if rule.max_weight is not None and weight > rule.max_weight:
                rejection_reasons.append(
                    f'Peso {weight}kg acima do maximo {rule.max_weight}kg'
                )

            # --- Soma das dimensoes ---
            if rule.min_sum_dimensions is not None and sum_dimensions < rule.min_sum_dimensions:
                rejection_reasons.append(
                    f'Soma das dimensoes {sum_dimensions}cm abaixo do minimo {rule.min_sum_dimensions}cm'
                )
            if rule.max_sum_dimensions is not None and sum_dimensions > rule.max_sum_dimensions:
                rejection_reasons.append(
                    f'Soma das dimensoes {sum_dimensions}cm acima do maximo {rule.max_sum_dimensions}cm'
                )

            # --- Maior lado individual ---
            if rule.max_single_side is not None and max_side > rule.max_single_side:
                rejection_reasons.append(
                    f'Maior lado {max_side}cm acima do maximo {rule.max_single_side}cm'
                )

            if rejection_reasons:
                ineligible.append({
                    'carrier_name': rule.carrier_name,
                    'modality': rule.modality,
                    'rule_id': rule.id,
                    'reasons': rejection_reasons,
                })
            else:
                eligible.append({
                    'carrier_name': rule.carrier_name,
                    'modality': rule.modality,
                    'rule_id': rule.id,
                })

                # --- Avisos (nao bloqueantes) ---
                if rule.non_mechanizable_threshold is not None:
                    if max_side > rule.non_mechanizable_threshold:
                        warnings.append({
                            'carrier_name': rule.carrier_name,
                            'modality': rule.modality,
                            'message': (
                                f'Pacote com lado de {max_side}cm excede '
                                f'{rule.non_mechanizable_threshold}cm. '
                                f'Pode haver taxa adicional de nao mecanizavel.'
                            ),
                        })

        return {
            'eligible': eligible,
            'ineligible': ineligible,
            'warnings': warnings,
            'package_info': {
                'height': float(height),
                'width': float(width),
                'length': float(length),
                'weight': float(weight),
                'sum_dimensions': float(sum_dimensions),
                'max_single_side': float(max_side),
            },
        }

    @staticmethod
    def filter_melhor_envio_quotes(
        quotes_data: list,
        height: Decimal,
        width: Decimal,
        length: Decimal,
        weight: Decimal,
    ) -> dict:
        """
        Filtra cotacoes do Melhor Envio removendo transportadoras incompativeis.

        Cruza o nome da transportadora retornado pelo Melhor Envio (company.name)
        com as regras cadastradas. Se a transportadora nao tem regra cadastrada,
        ela e mantida (nao bloqueada).

        Args:
            quotes_data: Lista de cotacoes retornadas pelo Melhor Envio
            height: Altura do pacote em cm
            width: Largura do pacote em cm
            length: Comprimento do pacote em cm
            weight: Peso do pacote em kg

        Returns:
            dict com:
                - filtered_quotes: lista de cotacoes validas
                - removed_quotes: lista de cotacoes removidas com motivos
                - warnings: avisos sobre taxas extras
        """
        if not isinstance(quotes_data, list):
            return {
                'filtered_quotes': quotes_data if quotes_data else [],
                'removed_quotes': [],
                'warnings': [],
            }

        validation = CarrierRuleService.validate_package(
            height=height,
            width=width,
            length=length,
            weight=weight,
        )

        # Construir set de transportadoras inelegiveis indexado por carrier_name
        ineligible_by_carrier = {}
        for item in validation['ineligible']:
            carrier = item['carrier_name'].lower().strip()
            if carrier not in ineligible_by_carrier:
                ineligible_by_carrier[carrier] = []
            ineligible_by_carrier[carrier].append(item)

        # Construir set de transportadoras elegiveis
        eligible_carriers = set()
        for item in validation['eligible']:
            eligible_carriers.add(item['carrier_name'].lower().strip())

        filtered_quotes = []
        removed_quotes = []

        for quote in quotes_data:
            if not isinstance(quote, dict):
                continue

            # Cotacoes com erro do Melhor Envio sao mantidas (ja vem com mensagem)
            if 'error' in quote:
                filtered_quotes.append(quote)
                continue

            # Extrair nome da transportadora da cotacao
            company = quote.get('company', {})
            if isinstance(company, dict):
                company_name = company.get('name', '').lower().strip()
            else:
                company_name = str(company).lower().strip()

            service_name = quote.get('name', '').lower().strip()

            if not company_name:
                # Sem nome de transportadora: manter
                filtered_quotes.append(quote)
                continue

            # Verificar se esta transportadora tem ALGUMA regra cadastrada
            has_rules = CarrierRule.objects.filter(
                carrier_name__iexact=company_name.strip(),
                is_active=True,
            ).exists()

            if not has_rules:
                # Transportadora sem regras cadastradas: manter (nao bloquear)
                filtered_quotes.append(quote)
                continue

            # Se a transportadora tem regras, verificar se alguma modalidade e elegivel
            if company_name in eligible_carriers:
                filtered_quotes.append(quote)
            else:
                # Todas as modalidades desta transportadora foram rejeitadas
                reasons = []
                for ineligible_item in ineligible_by_carrier.get(company_name, []):
                    reasons.extend(ineligible_item['reasons'])

                removed_quotes.append({
                    'service_id': quote.get('id'),
                    'service_name': quote.get('name', ''),
                    'company_name': company.get('name', '') if isinstance(company, dict) else str(company),
                    'reasons': list(set(reasons)),  # deduplica
                })

        return {
            'filtered_quotes': filtered_quotes,
            'removed_quotes': removed_quotes,
            'warnings': validation['warnings'],
        }

    @staticmethod
    @transaction.atomic
    def create_rule(
        carrier_name: str,
        modality: str,
        **kwargs,
    ) -> CarrierRule:
        """
        Cria uma nova regra de transportadora.

        Args:
            carrier_name: Nome da transportadora
            modality: Nome da modalidade/servico
            **kwargs: Campos opcionais (min_height, max_weight, etc.)

        Returns:
            CarrierRule criada

        Raises:
            ValueError: Se regra duplicada
        """
        rule = CarrierRule.objects.create(
            carrier_name=carrier_name,
            modality=modality,
            **kwargs,
        )
        logger.info(f'Regra de transportadora criada: {rule}')
        return rule

    @staticmethod
    @transaction.atomic
    def update_rule(rule_id: int, **kwargs) -> CarrierRule:
        """
        Atualiza uma regra de transportadora existente.

        Args:
            rule_id: ID da regra
            **kwargs: Campos a atualizar

        Returns:
            CarrierRule atualizada

        Raises:
            CarrierRule.DoesNotExist: Se regra nao encontrada
        """
        rule = CarrierRule.objects.get(id=rule_id)

        for field, value in kwargs.items():
            if hasattr(rule, field):
                setattr(rule, field, value)

        rule.save()
        logger.info(f'Regra de transportadora atualizada: {rule}')
        return rule

    @staticmethod
    @transaction.atomic
    def delete_rule(rule_id: int) -> None:
        """
        Remove uma regra de transportadora.

        Args:
            rule_id: ID da regra

        Raises:
            CarrierRule.DoesNotExist: Se regra nao encontrada
        """
        rule = CarrierRule.objects.get(id=rule_id)
        logger.info(f'Regra de transportadora removida: {rule}')
        rule.delete()

    @staticmethod
    def get_rules_for_carrier(carrier_name: str) -> list:
        """
        Retorna todas as regras ativas para uma transportadora.

        Args:
            carrier_name: Nome da transportadora

        Returns:
            QuerySet de CarrierRule
        """
        return CarrierRule.objects.filter(
            carrier_name__iexact=carrier_name,
            is_active=True,
        )
