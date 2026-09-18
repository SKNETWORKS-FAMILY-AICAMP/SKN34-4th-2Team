import { SelfIntroKeys, SelfIntroLabels, TechLevels } from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';

/**
 * 이력서 섹션 — features/resume/presentation/resume_edit_screen.dart의 양식.
 *
 * 항목 카드는 「항목 n」 머리와 칸 이름(회사명·전공·시작일…)을 그대로 쓴다.
 * Doc 보기는 같은 구조를 입력창 없이 읽기로만 보여 준다.
 */
export const nextId = (prefix: string) => `${prefix}${Date.now()}${Math.random().toString(36).slice(2, 5)}`;

export function period(start: string, end: string, isCurrent = false): string {
  const s = start.trim();
  const e = isCurrent ? '현재' : end.trim();
  if (s === '' && e === '') return '';
  if (s === '') return e;
  if (e === '') return s;
  return `${s} ~ ${e}`;
}

/** 편집용 한 칸 */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
}: {
  label: string;
  value: string;
  onChange(next: string): void;
  placeholder?: string;
  multiline?: boolean;
}) {
  return (
    <label className="item-field">
      <span className="item-field__label">{label}</span>
      {multiline ? (
        <textarea
          className="input input--area"
          rows={3}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="input"
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}

/** 읽기용 한 칸 */
export function ReadField({ label, value }: { label: string; value: string }) {
  return (
    <div className="item-field item-field--read">
      <span className="item-field__label">{label}</span>
      <p className={value.trim() === '' ? 'doc-read__empty' : undefined}>
        {value.trim() === '' ? '미작성' : value}
      </p>
    </div>
  );
}

export function ItemCard({
  index,
  onRemove,
  children,
}: {
  index: number;
  onRemove?(): void;
  children: React.ReactNode;
}) {
  return (
    <div className="item-card">
      <div className="item-card__head">
        <strong>항목 {index + 1}</strong>
        {onRemove !== undefined && (
          <button type="button" className="icon-btn" onClick={onRemove} aria-label="항목 삭제">
            <Icon name="delete" size={17} />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

export function AddItem({ onAdd, label = '항목 추가' }: { onAdd(): void; label?: string }) {
  return (
    <button type="button" className="add-row" onClick={onAdd}>
      <Icon name="add" size={18} />
      {label}
    </button>
  );
}

type Patch = (patch: Partial<ResumeContent>) => void;

/** 섹션 하나를 편집 또는 읽기로 그린다. */
export function SectionBody({
  sectionKey,
  resume,
  patch,
  readOnly,
}: {
  sectionKey: string;
  resume: Resume;
  patch: Patch;
  readOnly: boolean;
}) {
  const c = resume.content;

  switch (sectionKey) {
    case 'coreCompetencies':
      return readOnly ? (
        <p className={c.coreCompetencies.text.trim() === '' ? 'doc-read__empty' : 'doc-read__body'}>
          {c.coreCompetencies.text.trim() === '' ? '미작성' : c.coreCompetencies.text}
        </p>
      ) : (
        <textarea
          className="input input--area"
          rows={3}
          value={c.coreCompetencies.text}
          onChange={(e) => patch({ coreCompetencies: { text: e.target.value } })}
        />
      );

    case 'experience':
      return (
        <>
          {c.experience.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={
                readOnly
                  ? undefined
                  : () => patch({ experience: c.experience.filter((x) => x.id !== item.id) })
              }
            >
              {readOnly ? (
                <>
                  <ReadField label="회사명" value={item.company} />
                  <ReadField label="직무" value={item.role} />
                  <ReadField label="기간" value={period(item.startDate, item.endDate, item.isCurrent)} />
                  <ReadField label="설명" value={item.description} />
                </>
              ) : (
                <>
                  <Field
                    label="회사명"
                    value={item.company}
                    onChange={(v) =>
                      patch({ experience: c.experience.map((x) => (x.id === item.id ? { ...x, company: v } : x)) })
                    }
                  />
                  <Field
                    label="직무"
                    value={item.role}
                    onChange={(v) =>
                      patch({ experience: c.experience.map((x) => (x.id === item.id ? { ...x, role: v } : x)) })
                    }
                  />
                  <div className="item-row">
                    <Field
                      label="시작일"
                      value={item.startDate}
                      placeholder="2025-01"
                      onChange={(v) =>
                        patch({ experience: c.experience.map((x) => (x.id === item.id ? { ...x, startDate: v } : x)) })
                      }
                    />
                    <Field
                      label="종료일"
                      value={item.endDate}
                      placeholder="2025-06"
                      onChange={(v) =>
                        patch({ experience: c.experience.map((x) => (x.id === item.id ? { ...x, endDate: v } : x)) })
                      }
                    />
                  </div>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={item.isCurrent}
                      onChange={(e) =>
                        patch({
                          experience: c.experience.map((x) =>
                            x.id === item.id ? { ...x, isCurrent: e.target.checked } : x,
                          ),
                        })
                      }
                    />
                    <span>재직 중</span>
                  </label>
                  <Field
                    label="설명"
                    multiline
                    value={item.description}
                    onChange={(v) =>
                      patch({
                        experience: c.experience.map((x) => (x.id === item.id ? { ...x, description: v } : x)),
                      })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  experience: [
                    ...c.experience,
                    {
                      id: nextId('exp'),
                      company: '',
                      role: '',
                      startDate: '',
                      endDate: '',
                      isCurrent: false,
                      description: '',
                    },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'education':
      return (
        <>
          {c.education.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={
                readOnly ? undefined : () => patch({ education: c.education.filter((x) => x.id !== item.id) })
              }
            >
              {readOnly ? (
                <>
                  <ReadField label="학교명" value={item.school} />
                  <ReadField label="전공" value={item.major} />
                  <ReadField label="시작일" value={item.startDate} />
                  <ReadField label="종료일" value={item.endDate} />
                  <ReadField label="상태 (졸업/재학/수료)" value={item.status} />
                </>
              ) : (
                <>
                  <Field
                    label="학교명"
                    value={item.school}
                    onChange={(v) =>
                      patch({ education: c.education.map((x) => (x.id === item.id ? { ...x, school: v } : x)) })
                    }
                  />
                  <Field
                    label="전공"
                    value={item.major}
                    onChange={(v) =>
                      patch({ education: c.education.map((x) => (x.id === item.id ? { ...x, major: v } : x)) })
                    }
                  />
                  <div className="item-row">
                    <Field
                      label="시작일"
                      value={item.startDate}
                      placeholder="2020-03"
                      onChange={(v) =>
                        patch({ education: c.education.map((x) => (x.id === item.id ? { ...x, startDate: v } : x)) })
                      }
                    />
                    <Field
                      label="종료일"
                      value={item.endDate}
                      placeholder="2023-02"
                      onChange={(v) =>
                        patch({ education: c.education.map((x) => (x.id === item.id ? { ...x, endDate: v } : x)) })
                      }
                    />
                  </div>
                  <label className="item-field">
                    <span className="item-field__label">상태 (졸업/재학/수료)</span>
                    <select
                      className="input input--select"
                      value={item.status}
                      onChange={(e) =>
                        patch({
                          education: c.education.map((x) => (x.id === item.id ? { ...x, status: e.target.value } : x)),
                        })
                      }
                    >
                      {['졸업', '재학', '수료'].map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  education: [
                    ...c.education,
                    { id: nextId('edu'), school: '', major: '', startDate: '', endDate: '', status: '졸업' },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'techStack':
      return (
        <>
          <div className="tech-rows">
            {c.techStack.map((item) => (
              <div key={item.id} className="tech-row">
                {readOnly ? (
                  <>
                    <span className="skill-chip">{item.name}</span>
                    <span className="hint">{item.level}</span>
                  </>
                ) : (
                  <>
                    <input
                      className="input"
                      value={item.name}
                      placeholder="기술 이름"
                      onChange={(e) =>
                        patch({
                          techStack: c.techStack.map((x) => (x.id === item.id ? { ...x, name: e.target.value } : x)),
                        })
                      }
                    />
                    <select
                      className="input input--select"
                      value={item.level}
                      onChange={(e) =>
                        patch({
                          techStack: c.techStack.map((x) => (x.id === item.id ? { ...x, level: e.target.value } : x)),
                        })
                      }
                    >
                      {TechLevels.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="삭제"
                      onClick={() => patch({ techStack: c.techStack.filter((x) => x.id !== item.id) })}
                    >
                      <Icon name="delete" size={17} />
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
          {!readOnly && (
            <AddItem
              label="기술 추가"
              onAdd={() => patch({ techStack: [...c.techStack, { id: nextId('t'), name: '', level: '중급' }] })}
            />
          )}
        </>
      );

    case 'certifications':
      return (
        <>
          {c.certifications.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={
                readOnly
                  ? undefined
                  : () => patch({ certifications: c.certifications.filter((x) => x.id !== item.id) })
              }
            >
              {readOnly ? (
                <>
                  <ReadField label="자격증명" value={item.name} />
                  <ReadField label="발급기관" value={item.issuer} />
                  <ReadField label="취득일" value={item.acquiredDate} />
                </>
              ) : (
                <>
                  <Field
                    label="자격증명"
                    value={item.name}
                    onChange={(v) =>
                      patch({
                        certifications: c.certifications.map((x) => (x.id === item.id ? { ...x, name: v } : x)),
                      })
                    }
                  />
                  <Field
                    label="발급기관"
                    value={item.issuer}
                    onChange={(v) =>
                      patch({
                        certifications: c.certifications.map((x) => (x.id === item.id ? { ...x, issuer: v } : x)),
                      })
                    }
                  />
                  <Field
                    label="취득일"
                    value={item.acquiredDate}
                    placeholder="2026-06"
                    onChange={(v) =>
                      patch({
                        certifications: c.certifications.map((x) =>
                          x.id === item.id ? { ...x, acquiredDate: v } : x,
                        ),
                      })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  certifications: [
                    ...c.certifications,
                    { id: nextId('cert'), name: '', issuer: '', acquiredDate: '' },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'awards':
      return (
        <>
          {c.awards.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={readOnly ? undefined : () => patch({ awards: c.awards.filter((x) => x.id !== item.id) })}
            >
              {readOnly ? (
                <>
                  <ReadField label="수상명" value={item.name} />
                  <ReadField label="수여기관" value={item.organization} />
                  <ReadField label="수상일" value={item.date} />
                  <ReadField label="설명" value={item.description} />
                </>
              ) : (
                <>
                  <Field
                    label="수상명"
                    value={item.name}
                    onChange={(v) => patch({ awards: c.awards.map((x) => (x.id === item.id ? { ...x, name: v } : x)) })}
                  />
                  <Field
                    label="수여기관"
                    value={item.organization}
                    onChange={(v) =>
                      patch({ awards: c.awards.map((x) => (x.id === item.id ? { ...x, organization: v } : x)) })
                    }
                  />
                  <Field
                    label="수상일"
                    value={item.date}
                    placeholder="2025-10"
                    onChange={(v) => patch({ awards: c.awards.map((x) => (x.id === item.id ? { ...x, date: v } : x)) })}
                  />
                  <Field
                    label="설명"
                    multiline
                    value={item.description}
                    onChange={(v) =>
                      patch({ awards: c.awards.map((x) => (x.id === item.id ? { ...x, description: v } : x)) })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  awards: [
                    ...c.awards,
                    { id: nextId('aw'), name: '', organization: '', date: '', description: '' },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'trainingExperience':
      return (
        <>
          {c.trainingExperience.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={
                readOnly
                  ? undefined
                  : () => patch({ trainingExperience: c.trainingExperience.filter((x) => x.id !== item.id) })
              }
            >
              {readOnly ? (
                <>
                  <ReadField label="교육명" value={item.course} />
                  <ReadField label="기관" value={item.organization} />
                  <ReadField label="기간" value={period(item.startDate, item.endDate)} />
                  <ReadField label="설명" value={item.description} />
                </>
              ) : (
                <>
                  <Field
                    label="교육명"
                    value={item.course}
                    onChange={(v) =>
                      patch({
                        trainingExperience: c.trainingExperience.map((x) =>
                          x.id === item.id ? { ...x, course: v } : x,
                        ),
                      })
                    }
                  />
                  <Field
                    label="기관"
                    value={item.organization}
                    onChange={(v) =>
                      patch({
                        trainingExperience: c.trainingExperience.map((x) =>
                          x.id === item.id ? { ...x, organization: v } : x,
                        ),
                      })
                    }
                  />
                  <div className="item-row">
                    <Field
                      label="시작일"
                      value={item.startDate}
                      onChange={(v) =>
                        patch({
                          trainingExperience: c.trainingExperience.map((x) =>
                            x.id === item.id ? { ...x, startDate: v } : x,
                          ),
                        })
                      }
                    />
                    <Field
                      label="종료일"
                      value={item.endDate}
                      onChange={(v) =>
                        patch({
                          trainingExperience: c.trainingExperience.map((x) =>
                            x.id === item.id ? { ...x, endDate: v } : x,
                          ),
                        })
                      }
                    />
                  </div>
                  <Field
                    label="설명"
                    multiline
                    value={item.description}
                    onChange={(v) =>
                      patch({
                        trainingExperience: c.trainingExperience.map((x) =>
                          x.id === item.id ? { ...x, description: v } : x,
                        ),
                      })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  trainingExperience: [
                    ...c.trainingExperience,
                    {
                      id: nextId('tr'),
                      course: '',
                      organization: '',
                      startDate: '',
                      endDate: '',
                      description: '',
                    },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'otherActivities':
      return (
        <>
          {c.otherActivities.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={
                readOnly
                  ? undefined
                  : () => patch({ otherActivities: c.otherActivities.filter((x) => x.id !== item.id) })
              }
            >
              {readOnly ? (
                <>
                  <ReadField label="활동명" value={item.name} />
                  <ReadField label="기간" value={period(item.startDate, item.endDate)} />
                  <ReadField label="설명" value={item.description} />
                </>
              ) : (
                <>
                  <Field
                    label="활동명"
                    value={item.name}
                    onChange={(v) =>
                      patch({
                        otherActivities: c.otherActivities.map((x) => (x.id === item.id ? { ...x, name: v } : x)),
                      })
                    }
                  />
                  <div className="item-row">
                    <Field
                      label="시작일"
                      value={item.startDate}
                      onChange={(v) =>
                        patch({
                          otherActivities: c.otherActivities.map((x) =>
                            x.id === item.id ? { ...x, startDate: v } : x,
                          ),
                        })
                      }
                    />
                    <Field
                      label="종료일"
                      value={item.endDate}
                      onChange={(v) =>
                        patch({
                          otherActivities: c.otherActivities.map((x) =>
                            x.id === item.id ? { ...x, endDate: v } : x,
                          ),
                        })
                      }
                    />
                  </div>
                  <Field
                    label="설명"
                    multiline
                    value={item.description}
                    onChange={(v) =>
                      patch({
                        otherActivities: c.otherActivities.map((x) =>
                          x.id === item.id ? { ...x, description: v } : x,
                        ),
                      })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  otherActivities: [
                    ...c.otherActivities,
                    { id: nextId('ot'), name: '', startDate: '', endDate: '', description: '' },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'projects':
      return (
        <>
          {c.projects.map((item, i) => (
            <ItemCard
              key={item.id}
              index={i}
              onRemove={readOnly ? undefined : () => patch({ projects: c.projects.filter((x) => x.id !== item.id) })}
            >
              {readOnly ? (
                <>
                  <ReadField label="프로젝트명" value={item.name} />
                  <ReadField label="기간" value={period(item.startDate, item.endDate)} />
                  <ReadField label="역할" value={item.role} />
                  <ReadField label="사용 기술" value={item.techStack} />
                  <ReadField label="설명" value={item.description} />
                  <ReadField label="URL" value={item.url} />
                </>
              ) : (
                <>
                  <Field
                    label="프로젝트명"
                    value={item.name}
                    onChange={(v) =>
                      patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, name: v } : x)) })
                    }
                  />
                  <div className="item-row">
                    <Field
                      label="시작일"
                      value={item.startDate}
                      onChange={(v) =>
                        patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, startDate: v } : x)) })
                      }
                    />
                    <Field
                      label="종료일"
                      value={item.endDate}
                      onChange={(v) =>
                        patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, endDate: v } : x)) })
                      }
                    />
                  </div>
                  <Field
                    label="역할"
                    value={item.role}
                    onChange={(v) =>
                      patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, role: v } : x)) })
                    }
                  />
                  <Field
                    label="사용 기술"
                    value={item.techStack}
                    placeholder="Python · Pandas"
                    onChange={(v) =>
                      patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, techStack: v } : x)) })
                    }
                  />
                  <Field
                    label="설명"
                    multiline
                    value={item.description}
                    onChange={(v) =>
                      patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, description: v } : x)) })
                    }
                  />
                  <Field
                    label="URL"
                    value={item.url}
                    placeholder="https://github.com/..."
                    onChange={(v) =>
                      patch({ projects: c.projects.map((x) => (x.id === item.id ? { ...x, url: v } : x)) })
                    }
                  />
                </>
              )}
            </ItemCard>
          ))}
          {!readOnly && (
            <AddItem
              onAdd={() =>
                patch({
                  projects: [
                    ...c.projects,
                    {
                      id: nextId('prj'),
                      name: '',
                      startDate: '',
                      endDate: '',
                      role: '',
                      techStack: '',
                      description: '',
                      url: '',
                    },
                  ],
                })
              }
            />
          )}
        </>
      );

    case 'selfIntroduction':
      return (
        <div className="intro-list">
          {SelfIntroKeys.map((key) => {
            const part = c.selfIntroduction[key];
            return (
              <div key={key} className="intro-item">
                <strong className="intro-item__q">{SelfIntroLabels[key]}</strong>
                {readOnly ? (
                  <p className={part.body.trim() === '' ? 'doc-read__empty' : undefined}>
                    {part.body.trim() === '' ? '미작성' : part.body}
                  </p>
                ) : (
                  <textarea
                    className="input input--area"
                    rows={3}
                    value={part.body}
                    onChange={(e) =>
                      patch({
                        selfIntroduction: {
                          ...c.selfIntroduction,
                          [key]: { ...part, body: e.target.value },
                        },
                      })
                    }
                  />
                )}
              </div>
            );
          })}
        </div>
      );

    default:
      return null;
  }
}
