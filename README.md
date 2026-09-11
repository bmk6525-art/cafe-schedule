# 카페 통합 근무 스케줄 관리 프로그램

카페 직원과 파트타이머의 월별 근무 스케줄을 작성하고 관리하는 통합 관리 시스템입니다.

---

## 사용 기술

| 분류 | 기술 |
|------|------|
| Frontend | React 19, TypeScript, Vite 8 |
| Backend | Python 3.14, FastAPI 0.141 |
| Database | SQLite, SQLAlchemy 2.0 |
| API 통신 | Axios, React Router |

---

## 폴더 구조

```
CAFE SHCEDULE/
├── frontend/                  # React + TypeScript + Vite
│   └── src/
│       ├── components/        # 공통 컴포넌트
│       ├── pages/             # 페이지 컴포넌트
│       ├── layouts/           # 레이아웃 컴포넌트
│       ├── hooks/             # 커스텀 훅
│       ├── services/          # API 호출 함수
│       ├── types/             # TypeScript 타입 정의
│       └── utils/             # 유틸리티 함수
│
├── backend/                   # FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── main.py            # FastAPI 앱 진입점
│   │   ├── api/v1/            # REST API 엔드포인트
│   │   ├── models/            # SQLAlchemy 모델 (DB 테이블)
│   │   ├── schemas/           # Pydantic 스키마 (요청/응답)
│   │   ├── services/          # 비즈니스 로직
│   │   ├── repositories/      # DB 접근 레이어
│   │   ├── core/              # 설정값 관리
│   │   ├── database/          # DB 연결 및 Seed 데이터
│   │   ├── schedule_engine/   # 스케줄 자동 생성 (PHASE 6 예정)
│   │   ├── payroll_engine/    # 급여 계산 (PHASE 10 예정)
│   │   └── ai/                # Claude AI 연동 (PHASE 13 예정)
│   └── tests/                 # 테스트 코드
│
├── docs/                      # 문서
└── README.md
```

---

## 설치 방법

### 요구사항
- Python 3.10 이상
- Node.js 18 이상
- npm 9 이상

### Backend 설치

```bash
cd backend
pip install -r requirements.txt
```

### Frontend 설치

```bash
cd frontend
npm install
```

---

## Backend 실행 방법

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Frontend 실행 방법

```bash
cd frontend
npm run dev
```

실행 후 브라우저에서 http://localhost:5173 으로 접속합니다.

---

## 환경변수 설정 방법

### Backend (`backend/.env`)

```env
DATABASE_URL=sqlite:///./cafe_schedule.db
APP_ENV=development
DEBUG=true
FRONTEND_URL=http://localhost:5173
ANTHROPIC_API_KEY=              # PHASE 13에서 사용
SECRET_KEY=your-secret-key
```

### Frontend (`frontend/.env`)

```env
VITE_API_URL=http://localhost:8000
```

두 파일 모두 `.env.example`을 복사하여 만들 수 있습니다.

---

## 테스트 실행 방법

```bash
cd backend
python -m pytest tests/ -v
```

---

## 테스트 데이터 생성 (Seed)

Backend와 Frontend를 모두 실행한 후, 대시보드 화면에서
**"테스트 데이터 생성"** 버튼을 클릭하거나 다음 API를 직접 호출합니다:

```bash
curl -X POST http://localhost:8000/api/v1/seed
```

생성되는 데이터:
- 매장 3개: 1호점(10:00~23:00), 2호점(08:30~23:00), 3호점(09:00~23:00)
- 정규직 3명: 직원A, 직원B, 직원C
- 파트타이머 5명: 파트A, 파트B, 파트C, 파트D, 파트E

---

## 개발 단계 (PHASE)

| PHASE | 내용 | 상태 |
|-------|------|------|
| 1 | 프로젝트 기본 구조 + DB | ✅ 완료 |
| 2 | 직원 관리 | ⏳ 예정 |
| 3 | 매장 관리 | ⏳ 예정 |
| 4 | 파트타이머 가능/불가능 시간 관리 | ⏳ 예정 |
| 5 | 매장별 시간대 필요인원 관리 | ⏳ 예정 |
| 6 | 스케줄 자동 생성 엔진 | ⏳ 예정 |
| 7 | 스케줄 조회 및 수동 수정 | ⏳ 예정 |
| 8 | 스케줄 검증 | ⏳ 예정 |
| 9 | 실제 근무시간 관리 | ⏳ 예정 |
| 10 | 급여 및 주휴수당 계산 | ⏳ 예정 |
| 11 | 월별 저장/복사/마감 | ⏳ 예정 |
| 12 | 변경 이력 | ⏳ 예정 |
| 13 | Claude AI 연동 | ⏳ 예정 |
| 14 | 대시보드 및 통계 | ⏳ 예정 |

---

## API 엔드포인트 (PHASE 1 기준)

### 매장
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/v1/stores | 매장 목록 조회 |
| GET | /api/v1/stores/{id} | 매장 상세 조회 |
| POST | /api/v1/stores | 매장 추가 |
| PUT | /api/v1/stores/{id} | 매장 수정 |
| DELETE | /api/v1/stores/{id} | 매장 비활성화 |

### 직원
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/v1/employees | 직원 목록 조회 |
| GET | /api/v1/employees/{id} | 직원 상세 조회 |
| POST | /api/v1/employees | 직원 추가 |
| PUT | /api/v1/employees/{id} | 직원 수정 |
| DELETE | /api/v1/employees/{id} | 직원 비활성화 |

### 개발용
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /api/v1/seed | 테스트 데이터 생성 |
