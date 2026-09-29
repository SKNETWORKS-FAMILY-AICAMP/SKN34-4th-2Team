// 데모 이력서 본문을 JSON 으로 뽑는다 — AI 화면 예시 응답(mocks.mjs)이 같은 이력서를 쓰게.
import { writeFileSync } from 'node:fs';
import { seedResumes } from '../../src/data/seed';
const r = seedResumes.find((x) => x.id === 'r-demo-1')!;
writeFileSync(process.argv[2], JSON.stringify(r.content, null, 1));
