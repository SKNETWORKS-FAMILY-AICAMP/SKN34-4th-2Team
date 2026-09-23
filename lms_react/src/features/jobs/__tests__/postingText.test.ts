import { describe, expect, it } from 'vitest';

import { formatPostingText } from '../postingText';

const lines = (raw: string) => formatPostingText(raw).map((b) => `${b.type}:${b.text}`);

describe('공고 원문 정리', () => {
  it('사람인 — 혼자 있는 글머리표는 다음 줄과 한 항목, 이모지 소제목은 제목', () => {
    expect(lines('상세요강\n📋 주요업무\n•\nLLM 기반 AI 서비스 개발\n•\n데이터 구축/정비/연계\n📋 자격요건\n•\nPython으로 서비스 수준의 코드를 작성할 수 있는 분')).toEqual([
      'heading:주요업무',
      'item:LLM 기반 AI 서비스 개발',
      'item:데이터 구축/정비/연계',
      'heading:자격요건',
      'item:Python으로 서비스 수준의 코드를 작성할 수 있는 분',
    ]);
  });

  it('이모지만 있는 줄은 버리고, 아주 짧은 조각 · 괄호 조각은 앞줄에 잇는다', () => {
    expect(lines('•\nDocker 기반 배포 경험\n📄\n제출서류\n•\n이력서\n포지션\nAI\n애플리케이션 엔지니어\n(Generative AI / RAG) ( 0명 )')).toEqual([
      'item:Docker 기반 배포 경험',
      'heading:제출서류',
      'item:이력서',
      'heading:포지션',
      'text:AI 애플리케이션 엔지니어 (Generative AI / RAG) ( 0명 )',
    ]);
  });

  it('잡코리아 — 글자 꾸밈 단위로 조각난 항목을 한 문장으로 잇는다', () => {
    const raw =
      '자격요건\nㆍ\nPython\n프로그래밍 숙련\n:\n객체지향\n,\n모듈화\n,\n패키지 구조 설계 경험\nㆍ\nLLM API\n활용 경험\n: OpenAI, Anthropic, Gemini\n등\nAPI\n연동 및 결과 처리 경험\n우대사항\nㆍ\n벡터\nDB(Faiss, Pinecone\n등\n)\n연동 경험';
    expect(lines(raw)).toEqual([
      'heading:자격요건',
      'item:Python 프로그래밍 숙련: 객체지향, 모듈화, 패키지 구조 설계 경험',
      'item:LLM API 활용 경험: OpenAI, Anthropic, Gemini 등 API 연동 및 결과 처리 경험',
      'heading:우대사항',
      'item:벡터 DB(Faiss, Pinecone 등) 연동 경험',
    ]);
  });

  it('조사로 시작하는 조각은 앞말에 붙이고, 끝난 문장은 새 줄로 둔다', () => {
    expect(lines('하이브랩\n은\n즐겁게 일하며 함께 성장\n할 수 있는\n당신\n을 기다립니다.\n회사 소개 문단입니다.')).toEqual([
      'text:하이브랩은 즐겁게 일하며 함께 성장할 수 있는 당신을 기다립니다.',
      'text:회사 소개 문단입니다.',
    ]);
  });

  it('줄 앞 글머리표 · 번호 소제목 · 「라벨 :」 다음 값', () => {
    expect(lines('- LLM 기반 기능 개발\n- 프롬프트 설계\n1.\n백엔드 API개발\n·\nSpring Boot 기반 API 설계\n접수기간 :\n2026-09-07 ~ 2026-10-07')).toEqual([
      'item:LLM 기반 기능 개발',
      'item:프롬프트 설계',
      'sub:1. 백엔드 API개발',
      'item:Spring Boot 기반 API 설계',
      'heading:접수기간',
      'text:2026-09-07 ~ 2026-10-07',
    ]);
  });
});
