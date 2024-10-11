*********
Changelog
*********

.. seealso:: :ref:`howto_upgrade`


3.0.0rc1
========
| 학습과 추론시 필요한 상태 정보 가져오거나, 저장하기 위해서
| ``2.x.x`` 버전에서는 class 상속의 방식을 사용하였으나,
| ``3.x.x`` 버전부터는 context 객체를 전달함으로써 상태정보에 대한 읽기/저장 방식을 지원하도록 개편되었습니다.


Added
-----
* context: 학습/추론 작업에 대한 상태 정보를 가지고 있는 dictionarys
* pipeline: 학습의 단계(``pipeline``)별 인자(``argument``)와, 결과값(``result``)를 정보를 담고 있는 dictionary

Deprecations
------------

* Remove ``class Asset``.
