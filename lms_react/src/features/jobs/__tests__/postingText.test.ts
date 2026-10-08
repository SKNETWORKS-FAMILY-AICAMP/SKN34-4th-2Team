import { describe, expect, it } from 'vitest';

import { formatPostingText, isBrokenBody } from '../postingText';

const lines = (raw: string) => formatPostingText(raw).map((b) => `${b.type}:${'text' in b ? b.text : ''}`);

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

describe('수집 글의 찌꺼기와 조각', () => {
  it('이미지 속 글은 코드 껍데기를 벗겨 따로 모으고, 영어뿐인 줄 · 반복 줄은 뺀다', () => {
    const dump = (text: string) =>
      `array (\r\n  'status' => 'success',\r\n  'imageUrl' => 'https://x/y.png',\r\n  'reason' => '',\r\n  'text' => '${text}',\r\n)`;
    const raw = `노출지역\t서울 > 강서구\n${dump('dusk\r\n세상에 없던 브랜드를 만듭니다.\r\nWORK STATION\r\n365일 점심식대 지원\r\n365일 점심식대 지원')}\n${dump('-0-0-0-\r\n사내 피트니스')}`;
    expect(formatPostingText(raw)).toEqual([
      { type: 'form', rows: [{ label: '노출지역', value: '서울 > 강서구' }] },
      {
        type: 'image',
        urls: ['https://x/y.png'],
        lines: ['세상에 없던 브랜드를 만듭니다.', '365일 점심식대 지원', '사내 피트니스'],
      },
    ]);
  });

  it('페이지 안 탭 메뉴는 뒤에 같은 소제목이 나오면 뺀다', () => {
    const body = '일하는 방식\n주 5일 근무하고 출퇴근 시간은 자율로 정합니다.\n복지\n점심 식대를 매일 지원합니다.';
    expect(lines(`일하는 방식 · 복지 · 회사 소개\n${body}`)).toEqual(lines(body));
    expect(lines(body)).toContain('heading:복지');
    // 뒤에 같은 이름이 없으면 그냥 글이다
    expect(lines('Java · Spring · MySQL')).toEqual(['text:Java · Spring · MySQL']);
  });

  it('직무가 여럿이면 직무 이름 · 인원을 소제목으로 끊고, 빈 양식 문구는 뺀다', () => {
    const role = (name: string) => `${name}\n( 1명 )\n담당업무\nㆍ상세내용을 입력하세요\n우대사항\nㆍ운전가능자\nㆍ전공 : 미술학과, 건축학`;
    expect(lines(`${role('설계팀 -과장')}\n${role('차장급')}`)).toEqual([
      'role:설계팀 -과장 ( 1명 )',
      'sub:우대사항',
      'item:운전가능자',
      'item:전공 : 미술학과, 건축학',
      'role:차장급 ( 1명 )',
      'sub:우대사항',
      'item:운전가능자',
      'item:전공 : 미술학과, 건축학',
    ]);
  });

  it('표 머리칸 줄은 첫 제목만, 내용 없는 제목 · 사이트 제목은 뺀다', () => {
    // 새솔테크: 섹션 제목 「모집부문」 아래 표 머리칸 「모집부문 | 담당업무 | 자격사항 및 우대사항」
    expect(lines('나에게 딱 맞는 커리어만 매치, 사람인! | 취업, 채용, 커리어 매칭 플랫폼\n모집부문\n모집부문\n담당업무\n자격사항 및 우대사항\nTechnical Writer\nㆍ기술문서 작성')).toEqual([
      'heading:모집부문',
      'text:Technical Writer',
      'item:기술문서 작성',
    ]);
    // 사람인 양식의 빈 「복지 및 혜택」, 하위 칸만 든 「채용절차」
    expect(lines('🎁 복지 및 혜택\n채용절차\n접수기간\n2026-09-01 18시 ~ 채용시')).toEqual(['heading:접수기간', 'text:2026-09-01 18시 ~ 채용시']);
    // 내용이 있는 제목은 그대로
    expect(lines('자격요건\n- 학력 무관\n우대사항\n- 경력자 우대')).toEqual(['heading:자격요건', 'item:학력 무관', 'heading:우대사항', 'item:경력자 우대']);
  });

  it('묶은 제목 뒤에 같은 제목이 따로 나오면 그 부분을 뗀다', () => {
    expect(lines('포지션 및 자격요건\n편집 디자이너\n자격요건\n- 학력 무관')).toEqual([
      'heading:포지션',
      'text:편집 디자이너',
      'heading:자격요건',
      'item:학력 무관',
    ]);
    // 뒤에 따로 나오지 않으면 그대로
    expect(lines('포지션 및 자격요건\n- 학력 무관')[0]).toBe('heading:포지션 및 자격요건');
  });

  it('괄호로 여는 줄 · 괄호로 끝난 항목 뒤 짧은 조각은 앞 항목에 잇는다', () => {
    expect(lines('ㆍAdobe 프로그램 능숙자\n(인디자인, 일러스트, 포토샵)\nㆍ포트폴리오 제출 필수')).toEqual([
      'item:Adobe 프로그램 능숙자 (인디자인, 일러스트, 포토샵)',
      'item:포트폴리오 제출 필수',
    ]);
    expect(lines('ㆍMS Office(PowerPoint, Word, Excel)\n활용 능력 상급자')).toEqual(['item:MS Office(PowerPoint, Word, Excel) 활용 능력 상급자']);
  });

  it('직무별 표는 근무조건에서 찾은 직무 이름으로 조각난 자리도 소제목으로 끊는다', () => {
    const raw = [
      'ㆍ기술문서 작성', '자격사항', 'ㆍ4년제대학 졸업자',
      'ㆍ도메인 지식자', '사업본부', '제품 기획자', 'ㆍ시장 분석', '자격사항', 'ㆍ경력 5년 이상',
      '근무조건', 'Technical Writer', '1) 근무형태 : 정규직', '사업본부 제품 기획자', '1) 근무형태 : 정규직',
    ].join('\n');
    expect(lines(raw)).toEqual([
      'item:기술문서 작성',
      'heading:자격사항',
      'item:4년제대학 졸업자',
      'item:도메인 지식자',
      'role:사업본부 제품 기획자',
      'item:시장 분석',
      'sub:자격사항',
      'item:경력 5년 이상',
      'heading:근무조건',
      'text:Technical Writer',
      'sub:1) 근무형태 : 정규직',
      'role:사업본부 제품 기획자',
      'sub:1) 근무형태 : 정규직',
    ]);
  });

  it('장식 기호 · 글머리표를 단 섹션 이름, 묶은 섹션 이름은 제목이다', () => {
    expect(lines('ㆍ관련 자격증 보유하신 분\n◎ 근무조건\nㆍ근무형태 : 정규직\n┃ 복리후생\n- 4대 보험')).toEqual([
      'item:관련 자격증 보유하신 분',
      'heading:근무조건',
      'item:근무형태 : 정규직',
      'heading:복리후생',
      'item:4대 보험',
    ]);
    // 헤드헌터 공고: 「- 주요업무」. 항목으로 흔히 쓰는 「- 급여」는 그대로 항목
    expect(lines('- 주요업무\n- 고분자 제품 개발\n- 급여')).toEqual(['heading:주요업무', 'item:고분자 제품 개발', 'item:급여']);
    // 글머리표만 있는 줄 뒤의 이모지 제목
    expect(lines('📋 주요업무\n• 독성 연구 총괄\n•\n📋 자격요건\n• 경력 10년 이상')).toEqual([
      'heading:주요업무',
      'item:독성 연구 총괄',
      'heading:자격요건',
      'item:경력 10년 이상',
    ]);
    expect(lines('ㆍ콘텐츠 성과 개선\n지원자격 및 우대사항\nㆍ경력 3년 이상')[1]).toBe('heading:지원자격 및 우대사항');
  });

  it('구분선 · 사이트 꼬리말은 빼고, 웹 주소 뒤에 다음 줄을 붙이지 않는다', () => {
    expect(lines('담당업무\n-----------------\n- 기획\n************\nSaramin Recruitment Template')).toEqual(['heading:담당업무', 'item:기획']);
    expect(lines('------------ 기계, 전기 관련학과 신입사원')).toEqual(['text:기계, 전기 관련학과 신입사원']);
    expect(lines('홈페이지 https://www.imagebakery.tv/\n㈜시아디자인그룹은 이렇게 일해요')).toEqual([
      'text:홈페이지 https://www.imagebakery.tv/',
      'text:㈜시아디자인그룹은 이렇게 일해요',
    ]);
  });

  it('「항목명 : 값」 · 대괄호 머리말 · 번호 뒤 묶은 제목 · 구분선 경계 · 이어진 긴 주소', () => {
    expect(lines('기타사항\n- 접수기간 : 채용시 마감\n- 접수방법 : 홈페이지 지원')).toEqual([
      'heading:기타사항',
      'item:접수기간 : 채용시 마감',
      'item:접수방법 : 홈페이지 지원',
    ]);
    expect(lines('•\n[해외법인]\n홍콩 HK Dreamcos Co., Limited')).toEqual(['item:[해외법인] 홍콩 HK Dreamcos Co., Limited']);
    expect(lines('1.\n모집부문 및 자격요건\nㆍ경력 3년')[0]).toBe('sub:1. 모집부문 및 자격요건');
    expect(lines('- 세부 기준은 면접에서 안내합니다.\n-----------------\n포지션 소개\n본 포지션은 네트워크 장비만 다루지 않습니다.')).toEqual([
      'item:세부 기준은 면접에서 안내합니다.',
      'sub:포지션 소개',
      'text:본 포지션은 네트워크 장비만 다루지 않습니다.',
    ]);
    expect(lines('- 판매 페이지 : https://assetstore.unity.com/face-analyzer-\nfacial-landmarks-163114\n이 포지션의 AI 예상 면접 질문이 궁금하다면 점핏에서 확인해보세요!')).toEqual([
      'item:판매 페이지 : https://assetstore.unity.com/face-analyzer- facial-landmarks-163114',
    ]);
  });

  it('깨진 이모지 「??」 · 한정어 붙은 섹션 이름 · 「포지션」 뒤 인원 · 영어 항목', () => {
    expect(lines('ㆍ현실적인 기획안을 중요하게 평가합니다.\n?? 우대사항\n* PM 경험')).toEqual([
      'item:현실적인 기획안을 중요하게 평가합니다.',
      'heading:우대사항',
      'item:PM 경험',
    ]);
    expect(lines('근무지\nㆍ서울\n공통 자격요건\nㆍ경력 2년 이상')).toEqual(['heading:근무지', 'item:서울', 'heading:공통 자격요건', 'item:경력 2년 이상']);
    expect(lines('포지션 및 자격요건\n포지션\n( 1명 )\n담당업무\nㆍ서버 개발')).toEqual(['heading:담당업무', 'item:서버 개발']);
    expect(
      lines(
        '•    Lead major brand collaboration or awareness-building initiatives\nExperience & Education:\nBachelor Degree in Business or Marketing preferred\n10+ years of experience in marketing or product management',
      ),
    ).toEqual([
      'item:Lead major brand collaboration or awareness-building initiatives',
      'sub:Experience & Education',
      'text:Bachelor Degree in Business or Marketing preferred',
      'text:10+ years of experience in marketing or product management',
    ]);
    // 영어 낱말 조각은 지금처럼 잇는다
    expect(lines('•\nLLM API\nintegration')).toEqual(['item:LLM API integration']);
  });

  it('수집 때 받은 사이트 안내 페이지(깨진 글자)를 알아본다', () => {
    expect(isBrokenBody('ë³´ìì ì±\nì´ë©ì¼: helpdesk@albamon.com')).toBe(true);
    expect(isBrokenBody('ë³´ìì ì± '.repeat(10))).toBe(true);
    expect(isBrokenBody('자격요건\n- Python 경험 3년 이상 (Café 운영 경험 우대)')).toBe(false);
  });

  it('바로 뒤에 통째로 한 번 더 들어온 구간은 한 번만 보여 준다', () => {
    const run = '기간과 근무지역\n- 기간: 투입 후 10~12개월\n- 근무지역: 을지로 또는 수내역 인근';
    expect(lines(`${run}\n${run}\n전형절차`)).toEqual(lines(`${run}\n전형절차`));
    // 짧은 조각이 되풀이되는 것(「,」 「등」)은 건드리지 않는다
    expect(lines('Java\n,\nSpring\nJava\n,\nSpring').join(' ').match(/Spring/g)).toHaveLength(2);
  });

  it('세 줄로 나뉜 대괄호 소제목은 소제목이다', () => {
    expect(lines('[\n자격요건\n]\n-\n학력 무관\n[\n우대사항\n]\n- 경력자 우대')).toEqual([
      'heading:자격요건',
      'item:학력 무관',
      'heading:우대사항',
      'item:경력자 우대',
    ]);
  });

  it('번호 소제목은 번호마다 끊고, 긴 번호 줄은 문단, º 는 글머리표다', () => {
    expect(lines('1) 근무형태\n- 정규직\n2) 급여조건 : 면접 후 결정\n3) 근무시간\n- 주 40시간')).toEqual([
      'sub:1) 근무형태',
      'item:정규직',
      'sub:2) 급여조건 : 면접 후 결정',
      'sub:3) 근무시간',
      'item:주 40시간',
    ]);
    expect(lines('2) 경력 3년 이상\n3) 반도체 개발 관련 Tool (Layout Drawing, Device simulation) 역량 보유자')).toEqual([
      'sub:2) 경력 3년 이상',
      'text:3) 반도체 개발 관련 Tool (Layout Drawing, Device simulation) 역량 보유자',
    ]);
    expect(lines('º 브랜드 방향에 맞는 디자인 개발\nº 트렌드 분석')).toEqual(['item:브랜드 방향에 맞는 디자인 개발', 'item:트렌드 분석']);
  });

  it('끝난 목록 항목은 뒤 글을 삼키지 않고, 영어 대문자 소제목을 알아본다', () => {
    const raw = '우대사항\n-\n테스트 커버리지 개선에 관심 있는 분\nTECH STACK\n우리가 사용하는 기술\nAWS EC2\nOUR PEOPLE\n함께 성장하며 새로운 기준을 만들어갈 동료를 기다립니다.';
    expect(lines(raw)).toEqual([
      'heading:우대사항',
      'item:테스트 커버리지 개선에 관심 있는 분',
      'heading:TECH STACK',
      'text:우리가 사용하는 기술',
      'text:AWS EC2',
      'heading:OUR PEOPLE',
      'text:함께 성장하며 새로운 기준을 만들어갈 동료를 기다립니다.',
    ]);
    // 끝나지 않은 항목의 조각은 지금처럼 잇는다(잡코리아)
    expect(lines('•\nPython\n프로그래밍 숙련\n: 객체지향')).toEqual(['item:Python 프로그래밍 숙련: 객체지향']);
    // 끝난 항목 뒤 긴 줄은 새 문단
    expect(lines('- 경력 3년 이상인 분\n연봉은 면접 후 협의하여 결정합니다')).toEqual([
      'item:경력 3년 이상인 분',
      'text:연봉은 면접 후 협의하여 결정합니다',
    ]);
  });

  it('조각난 번호 소제목은 잇고, 01 · 02 는 번호다', () => {
    expect(lines('2.\n지원\n자격 및 역량\n·\n경력 15년 이상')).toEqual(['sub:2. 지원 자격 및 역량', 'item:경력 15년 이상']);
    expect(lines('매년 두 배로 성장하는 팀\n02\nA to Z 를 경험하는 조직')[1]).toBe('sub:02 A to Z 를 경험하는 조직');
  });
});

describe('사람인 간편 양식 공고', () => {
  // 2026-09-30 CJ ENM 「2026 신입사원 모집」 원문(줄여 옮김). 칸 이름과 값이 탭으로 나뉜다
  const RAW = [
    '상세요강',
    'CJ ENM 커머스부문',
    '      2026 신입사원 모집',
    '      업종\t방송사·케이블 > 미디어',
    '      직종\t선택 : 기획·전략 > 직무·직업 > 마케팅기획',
    '      선택 : 기획·전략 > 전문분야 > 트렌드분석',
    '      선택 : 마케팅·홍보·조사 > 직무·직업 > 마케팅',
    '      선택 : 마케팅·홍보·조사 > 직무·직업 > 마케팅기획',
    '      선택 : 기획·전략 > 직무·직업 > 마케팅기획',
    '      근무지 주소\t(06761) 서울 서초구 과천대로 870-13',
    '      노출지역\t서울 > 서초구',
  ].join('\n');

  it('칸 이름 · 값은 표로, 직종 분류는 대분류별 묶음으로', () => {
    const blocks = formatPostingText(RAW);
    expect(blocks.slice(0, 2)).toEqual([
      { type: 'text', text: 'CJ ENM 커머스부문' },
      { type: 'text', text: '2026 신입사원 모집' },
    ]);
    expect(blocks[2]).toEqual({
      type: 'form',
      rows: [
        { label: '업종', value: '방송사·케이블 > 미디어' },
        {
          label: '직종',
          groups: [
            { name: '기획·전략', items: ['마케팅기획', '트렌드분석'] },
            { name: '마케팅·홍보·조사', items: ['마케팅', '마케팅기획'] },
          ],
        },
        { label: '근무지 주소', value: '(06761) 서울 서초구 과천대로 870-13' },
        { label: '노출지역', value: '서울 > 서초구' },
      ],
    });
  });

  it('값 앞 쌍점은 떼고, 탭에 끊긴 소제목은 표로 보지 않는다', () => {
    expect(formatPostingText('근무형태\t:\t정규직(인턴:3개월)')).toEqual([
      { type: 'form', rows: [{ label: '근무형태', value: '정규직(인턴:3개월)' }] },
    ]);
    expect(lines('지원자격\t및 우대사항\n접수방법 및\t기간\n접수기간\t:').every((l) => !l.startsWith('form'))).toBe(true);
  });

  it('탭이 없는 보통 글은 그대로 문단이다', () => {
    expect(lines('자격요건\nPython 경험 3년 이상')).toEqual(['heading:자격요건', 'text:Python 경험 3년 이상']);
  });
});
