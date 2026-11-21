import { clearConsent } from '@/utils/cookieConsent'

// ─── Table helpers ────────────────────────────────────────────────────────────

interface CookieRow {
  name: string
  purpose: string
  duration: string
}

interface CookieTableProps {
  category: string
  description: string
  rows: CookieRow[]
}

function CookieTable({ category, description, rows }: CookieTableProps) {
  return (
    <div className="mb-8">
      {/* h3 com tamanho legivel e cor de destaque — diferenciado do h2 */}
      <h3 className="text-lg font-semibold text-gold mb-1">{category}</h3>
      <p className="text-sm text-ink-2 mb-3 leading-relaxed">{description}</p>
      {/* overflow-x-auto garante scroll horizontal em mobile sem quebrar o layout */}
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-sm min-w-[480px]">
          <thead>
            <tr className="bg-bg-3 border-b border-white/10">
              <th className="text-left px-4 py-3 font-semibold text-ink-1 w-1/3">
                Nome
              </th>
              <th className="text-left px-4 py-3 font-semibold text-ink-1 w-1/2">
                Finalidade
              </th>
              <th className="text-left px-4 py-3 font-semibold text-ink-1 whitespace-nowrap">
                Duração
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={row.name}
                // Striped: linhas pares com fundo levemente escuro para facilitar leitura
                className={`border-b border-white/5 last:border-0 transition-colors hover:bg-gold/5 ${
                  index % 2 === 0 ? 'bg-bg-2' : 'bg-bg-1'
                }`}
              >
                <td className="px-4 py-3 font-mono text-xs text-gold align-top">
                  {row.name}
                </td>
                <td className="px-4 py-3 text-ink-1 align-top leading-relaxed">
                  {row.purpose}
                </td>
                <td className="px-4 py-3 text-ink-3 whitespace-nowrap align-top">
                  {row.duration}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Cookie data ──────────────────────────────────────────────────────────────

const ESSENTIAL_COOKIES: CookieRow[] = [
  {
    name: 'access_token',
    purpose: 'Autenticação do usuário — mantém a sessão ativa após o login',
    duration: 'Sessão',
  },
  {
    name: 'cart_items',
    purpose: 'Itens adicionados ao carrinho de compras',
    duration: '30 dias',
  },
  {
    name: 'megdev_cookie_consent',
    purpose: 'Registro do consentimento de cookies do usuário',
    duration: '1 ano',
  },
]

const FUNCTIONAL_COOKIES: CookieRow[] = [
  {
    name: 'user_preferences',
    purpose: 'Preferências de interface, como idioma e configurações visuais',
    duration: '1 ano',
  },
]

const ANALYTICS_COOKIES: CookieRow[] = [
  {
    name: '_ga',
    purpose: 'Google Analytics — identifica usuários únicos para análise de tráfego',
    duration: '2 anos',
  },
  {
    name: '_gid',
    purpose: 'Google Analytics — distingue sessões de um mesmo usuário',
    duration: '24 horas',
  },
]

const MARKETING_COOKIES: CookieRow[] = [
  {
    name: '_fbp',
    purpose: 'Meta Pixel — rastreamento de conversões e personalização de anúncios no Facebook e Instagram',
    duration: '3 meses',
  },
]

// ─── Section component ────────────────────────────────────────────────────────

interface SectionProps {
  id: string
  title: string
  children: React.ReactNode
}

function Section({ id, title, children }: SectionProps) {
  return (
    <section id={id} className="mb-12">
      {/* h2 bem diferenciado do h3 em tamanho, peso e decoracao */}
      <h2 className="font-display text-2xl md:text-[28px] font-bold text-ink-1 tracking-[-0.02em] mb-4 pb-2 border-b border-gold/30">
        {title}
      </h2>
      {children}
    </section>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function CookiePolicy() {
  function handleManagePreferences() {
    clearConsent()
    window.location.reload()
  }

  return (
    <div className="min-h-screen bg-bg-0 pb-16">
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* h1 — topo da hierarquia, claramente maior que os h2 */}
      <h1 className="font-display text-3xl md:text-4xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
        Política de Cookies
      </h1>
      <p className="text-sm text-ink-3 mb-10">
        Última atualização: abril de 2026
      </p>

      {/* 1. O que são cookies */}
      <Section id="o-que-sao" title="1. O que são cookies">
        <p className="text-ink-1 leading-relaxed mb-4">
          Cookies são pequenos arquivos de texto armazenados no seu navegador
          quando você visita um site. Eles permitem que o site reconheça seu
          dispositivo em visitas futuras, mantendo preferências e informações de
          sessão.
        </p>
        <p className="text-ink-1 leading-relaxed">
          Utilizamos tanto cookies de sessão (apagados ao fechar o navegador)
          quanto cookies persistentes (permanecem por um período determinado).
          Nenhum cookie armazena informações pessoais sensíveis como senhas ou
          dados de pagamento.
        </p>
      </Section>

      {/* 2. Quais cookies usamos */}
      <Section id="quais-cookies" title="2. Quais cookies usamos">
        <p className="text-ink-1 leading-relaxed mb-6">
          Organizamos os cookies em quatro categorias conforme sua finalidade:
        </p>

        <CookieTable
          category="Essenciais"
          description="Necessários para o funcionamento básico do site. Não podem ser desativados pois o site não funciona sem eles."
          rows={ESSENTIAL_COOKIES}
        />

        <CookieTable
          category="Funcionais"
          description="Melhoram a experiência ao lembrar de suas preferências e configurações entre visitas."
          rows={FUNCTIONAL_COOKIES}
        />

        <CookieTable
          category="Analytics"
          description="Coletam dados anônimos sobre como os visitantes usam o site, ajudando a identificar melhorias."
          rows={ANALYTICS_COOKIES}
        />

        <CookieTable
          category="Marketing"
          description="Usados por parceiros de publicidade para exibir anúncios relevantes com base no seu perfil de navegação."
          rows={MARKETING_COOKIES}
        />
      </Section>

      {/* 3. Como gerenciar */}
      <Section id="como-gerenciar" title="3. Como gerenciar seus cookies">
        <p className="text-ink-1 leading-relaxed mb-4">
          Você pode gerenciar suas preferências de cookies a qualquer momento:
        </p>
        {/*
          list-outside com pl-5 resolve o problema de indentacao de itens longos
          com <strong> em mobile que list-inside causava
        */}
        <ul className="list-disc list-outside pl-5 space-y-3 text-ink-1 marker:text-gold mb-6">
          <li className="leading-relaxed">
            <strong>Pelo nosso banner:</strong> clique em "Personalizar" no banner
            de consentimento que aparece na primeira visita.
          </li>
          <li className="leading-relaxed">
            <strong>Pela sua conta:</strong> acesse{' '}
            <a href="/account?section=notifications" className="text-gold underline underline-offset-2 hover:text-gold/80 font-medium">
              Minha Conta → Notificações
            </a>{' '}
            e clique em "Gerenciar" na seção de Preferências de cookies.
          </li>
          <li className="leading-relaxed">
            <strong>Pelo navegador:</strong> todos os navegadores modernos permitem
            visualizar, bloquear e excluir cookies nas configurações de privacidade.
          </li>
        </ul>
        <div className="bg-gold/10 border border-gold/30 rounded-lg p-4 text-sm text-gold leading-relaxed">
          <strong>Atenção:</strong> desativar cookies essenciais pode impedir o
          funcionamento correto do login, do carrinho e de outras funcionalidades
          críticas.
        </div>
      </Section>

      {/* 4. Seus direitos (LGPD) */}
      <Section id="lgpd" title="4. Seus direitos (LGPD)">
        <p className="text-ink-1 leading-relaxed mb-4">
          De acordo com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018),
          você tem os seguintes direitos como titular de dados:
        </p>
        <ul className="list-disc list-outside pl-5 space-y-3 text-ink-1 marker:text-gold">
          <li className="leading-relaxed">
            <strong>Confirmação e acesso:</strong> confirmar se tratamos seus dados
            e acessar quais dados possuímos.
          </li>
          <li className="leading-relaxed">
            <strong>Correção:</strong> solicitar a correção de dados incompletos,
            inexatos ou desatualizados.
          </li>
          <li className="leading-relaxed">
            <strong>Anonimização ou eliminação:</strong> solicitar a anonimização
            ou exclusão de dados desnecessários ou tratados em desconformidade.
          </li>
          <li className="leading-relaxed">
            <strong>Portabilidade:</strong> solicitar a transferência dos seus
            dados a outro fornecedor de serviço.
          </li>
          <li className="leading-relaxed">
            <strong>Revogação do consentimento:</strong> retirar seu consentimento
            a qualquer momento, sem prejuízo dos tratamentos já realizados.
          </li>
          <li className="leading-relaxed">
            <strong>Oposição:</strong> opor-se ao tratamento realizado com
            fundamento em uma das hipóteses de dispensa de consentimento.
          </li>
        </ul>
      </Section>

      {/* 5. Contato */}
      <Section id="contato" title="5. Contato">
        <p className="text-ink-1 leading-relaxed mb-4">
          Para exercer seus direitos ou esclarecer dúvidas sobre esta política,
          entre em contato com nosso Encarregado de Proteção de Dados (DPO):
        </p>
        <div className="bg-bg-1 border border-white/10 rounded-lg p-4 space-y-2 text-sm text-ink-1">
          <p>
            <strong>Empresa:</strong> Grupo China Source Trade Ltda
          </p>
          <p>
            <strong>CNPJ:</strong> 44.933.523/0001-66
          </p>
          <p>
            <strong>Endereço:</strong> Av. Paulista, 171 — Bela Vista, São Paulo – SP
          </p>
          <p>
            <strong>E-mail:</strong>{' '}
            <a
              href="mailto:privacidade@megdev.com.br"
              className="text-gold underline underline-offset-2 hover:text-gold/80 font-medium"
            >
              privacidade@megdev.com.br
            </a>
          </p>
        </div>
      </Section>

      {/* Botao gerenciar preferencias — destaque prominente no final */}
      <div className="border-t border-gold/30 pt-10 mt-4">
        <p className="text-sm text-ink-2 mb-5 leading-relaxed">
          Deseja revisar ou alterar suas escolhas de cookies? Clique abaixo para
          redefinir suas preferências — o banner de consentimento será exibido
          novamente.
        </p>
        <button
          type="button"
          onClick={handleManagePreferences}
          className="w-full sm:w-auto bg-gold text-gold-deep px-8 py-3 rounded-xl text-sm font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus:ring-2 focus:ring-gold/40 focus:ring-offset-2 focus:ring-offset-bg-0"
        >
          Gerenciar minhas preferências de cookies
        </button>
      </div>
    </div>
    </div>
  )
}
