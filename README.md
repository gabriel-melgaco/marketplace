Academia Marketplace – Frontend

Frontend do Academia Marketplace, uma plataforma web para compra, venda e anúncio de equipamentos e produtos fitness.
Este repositório contém toda a interface do usuário, autenticação, navegação e integração com a API backend.

🚀 Tecnologias Utilizadas

React 18

TypeScript

Vite

React Router DOM

Tailwind CSS

Axios

Context API (autenticação)

JWT (via backend)

WireGuard VPN (ambiente de desenvolvimento)

📁 Estrutura de Pastas
src/
├── api/ # Configuração do Axios
├── assets/ # Imagens, logos e ícones
├── components/
│ ├── layout/ # Header, BottomNav, Footer, Layouts
│ └── ui/ # Componentes reutilizáveis (Input, Sidebar, etc.)
├── contexts/ # Context API (AuthContext)
├── pages/
│ ├── public/ # Páginas públicas
│ ├── auth/ # Login, registro, recuperação de senha
│ ├── checkout/ # Checkout, pagamento e confirmação
│ └── dashboard/ # Área do usuário (privada)
├── routes/ # Configuração de rotas
├── services/ # Serviços (authService, etc.)
├── types/ # Tipagens TypeScript
├── utils/ # Utilitários (tokenStorage, helpers)
├── App.tsx
└── main.tsx

🌐 Rotas da Aplicação
Públicas

/ – Home

/productlist

/productdetail/:id

/login

/register

/forgotpassword

/resetpassword

Privadas (requer autenticação)

/dashboard

/ad/:id

/mypurchase

/mysales

/myreviews

/checkout

/payment

/orderconfirmed

🔐 Autenticação

A autenticação é baseada em JWT, utilizando:

AuthContext para estado global

authService para comunicação com a API

Token Storage centralizado

Rotas privadas protegidas por PrivateRoutes

Fluxo:

Login → API retorna access token

Token salvo localmente

Context atualiza usuário autenticado

Layout e Header reagem automaticamente ao estado de login

🧩 Layout

A aplicação utiliza layouts distintos:

HomeLayout
Header + Outlet + BottomNav

Auth Pages
Login, Cadastro e Recuperação de senha sem Header/BottomNav

Private Routes
Protegidas por autenticação, reutilizando o layout principal

🎨 Estilização

Tailwind CSS

Design responsivo (mobile-first)

Header fixo

Bottom Navigation para mobile

Sidebar / Drawer lateral

Estados visuais claros (hover, active, focus)

🔌 Integração com API

Axios configurado com baseURL

Interceptors preparados para autenticação

Backend acessado via VPN WireGuard

Tratamento de erros (401, 400, etc.)

🛠️ Instalação e Execução
Pré-requisitos

Node.js 18+

npm ou yarn

Acesso à VPN (ambiente de desenvolvimento)
Status do Projeto

✔ Login
✔ Cadastro
✔ Autenticação com Context API
✔ Layout e Navegação
✔ Integração com API
🚧 Funcionalidades avançadas em desenvolvimento

👨‍💻 Autores

Frontend: Tharick Abreu

Backend: [Repositório separado]
