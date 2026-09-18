import pytest

from app.technology import canonical_technology, comparison_terms, technology_in_text


@pytest.mark.parametrize('name', ['파이썬', 'python', 'Python', 'Ｐｙｔｈｏｎ'])
def test_python_aliases(name):
    assert canonical_technology(name) == 'Python'


def test_korean_particle_and_case():
    assert comparison_terms('파이썬으로 개발했습니다.') == comparison_terms('Python으로 개발했습니다.')
    assert technology_in_text('파이썬', 'PYTHON 개발 경험')


def test_related_technologies_are_not_equivalent():
    assert not technology_in_text('Java', 'JavaScript 개발')
    assert not technology_in_text('Spring', 'Spring Boot 개발')
    assert not technology_in_text('React', 'React Native 개발')
    assert not technology_in_text('Python', 'CPython')
    assert comparison_terms('도커로 배포') - comparison_terms('파이썬으로 개발') == {'tech:Docker'}


def test_punctuation_and_unknown_preserved():
    assert technology_in_text('ReactJS', 'React.js, TypeScript')
    assert canonical_technology('UnlistedTool') == 'UnlistedTool'
    assert technology_in_text('C++', 'C++ 개발')
