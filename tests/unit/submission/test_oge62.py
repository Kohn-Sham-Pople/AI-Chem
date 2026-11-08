"""Hand-authored public OGE syntax; no captured private scheduler data."""
import time
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

from ai_chem_input.errors import InputError
from ai_chem_input.submission.sge import fields,parse_detail,parse_accounting,timestamp


FIXTURES=Path('tests/fixtures/sge_synthetic')


def test_oge_accounting_fields_do_not_swallow_the_time_colon():
    result=fields((FIXTURES/'oge_6_2u7_qacct_single.txt').read_bytes())
    assert result['qsub_time']=='Mon Nov  9 00:52:42 2026'
    assert result['start_time']=='Mon Nov  9 00:52:45 2026'
    assert result['end_time']=='Mon Nov  9 00:52:46 2026'
    assert result['jobnumber']=='1001' and result['taskid']=='undefined'
    assert 'pe_taskid' not in result


@pytest.mark.parametrize('data,key,value',[
    (b'job_number: 1001\n','job_number','1001'),
    (b'parallel environment: mpi_32 range: 32\n','parallel environment','mpi_32 range: 32'),
    (b'hard resource_list: h_rt=00:05:00\n','hard resource_list','h_rt=00:05:00'),
    (b'soft resource_list: synthetic_resource=1\n','soft resource_list','synthetic_resource=1'),
    (b'scheduling info: SYNTHETIC disabled\n','scheduling info','SYNTHETIC disabled'),
    (b'qsub_time\tSat Nov  7 14:12:46 2026\n','qsub_time','Sat Nov  7 14:12:46 2026'),
    (b'path /SYNTHETIC/value:with:colons\n','path','/SYNTHETIC/value:with:colons'),
])
def test_field_delimiters_are_unambiguous(data,key,value):
    assert fields(data)=={key:value}


@pytest.mark.parametrize('data',[
    b'1name value\n',b'bad-name: value\n',b'bad/name value\n',
    b'job_number : 1001\n',b': value\n',
    b'parallel  environment: mpi_32 range: 32\n',b'jobnumber\n',
    b'jobnumber 1001\njobnumber 1002\n',
    b'jobnumber: 1001\njobnumber 1001\n',
    b'parallel environment: mpi_32 range: 32\nparallel environment: mpi_32 range: 32\n',
    b'\xff\n',b'owner: synthetic\x00_owner\n',
])
def test_bad_or_duplicate_fields_still_block(data):
    with pytest.raises(InputError): fields(data)


@pytest.mark.parametrize('raw,zone,expected',[
    ('Mon Nov  9 00:52:42 2026','Asia/Seoul',1794153162.0),
    ('Sat Nov  7 14:12:46 2026','Asia/Seoul',1794028366.0),
    ('Mon Nov  9 00:52:42 2026','UTC',1794185562.0),
    ('1794153162',None,1794153162.0),
    ('1794153162.25','Asia/Seoul',1794153162.25),
    ('2026-11-09T00:52:42+09:00',None,1794153162.0),
    ('2026-11-08T15:52:42Z','Asia/Seoul',1794153162.0),
    ('2026-11-08T15:52:42+00:00','UTC',1794153162.0),
])
def test_oge_and_absolute_dates_have_exact_utc_values(raw,zone,expected):
    assert timestamp(raw,cluster_timezone=zone)==expected


@pytest.mark.parametrize('raw',[
    'Tue Nov  9 00:52:42 2026', # wrong weekday
    'Mon Feb 30 00:52:42 2026',
    'Mon Nov  9 24:52:42 2026','Mon Nov  9 00:60:42 2026',
    'Mon Nov  9 00:52:60 2026','Mon Foo  9 00:52:42 2026',
    'Mon Nov  9 00:52:42 2026 KST','Mon Nov  9 00:52:42',
    'Mon Nov  9 00:52:42 0000','2026-11-09T00:52:42',
    '09/11/2026 00:52:42','Mon Jan  1 00:00:00 0001','NaN','Infinity','9'*400,
])
def test_invalid_or_ambiguous_date_syntax_blocks(raw):
    with pytest.raises(InputError): timestamp(raw,cluster_timezone='Asia/Seoul')


@pytest.mark.parametrize('zone',[None,'KST','Unknown/Zone','America/New_York'])
def test_oge_date_requires_explicit_supported_cluster_zone(zone):
    with pytest.raises(InputError) as exc:
        timestamp('Mon Nov  9 00:52:42 2026',cluster_timezone=zone)
    assert exc.value.code=='SGE_TIMEZONE_UNKNOWN'


@pytest.mark.parametrize('raw',['1794153162','2026-11-08T15:52:42Z'])
def test_unknown_explicit_zone_cannot_be_hidden_by_an_absolute_date(raw):
    with pytest.raises(InputError): timestamp(raw,cluster_timezone='Unknown/Zone')


@pytest.mark.parametrize('raw',['Sun Oct  9 02:30:00 1988','Sun May  8 02:30:00 1988'])
def test_korean_historical_fold_and_gap_are_not_guessed(raw):
    with pytest.raises(InputError) as exc: timestamp(raw,cluster_timezone='Asia/Seoul')
    assert exc.value.code=='SGE_TIME_AMBIGUOUS'


@pytest.mark.parametrize('host_zone',['UTC0','HST10','JST-9'])
def test_process_local_zone_does_not_change_oge_interpretation(monkeypatch,host_zone):
    try:
        with monkeypatch.context() as patch:
            patch.setenv('TZ',host_zone); time.tzset()
            assert timestamp('Mon Nov  9 00:52:42 2026',cluster_timezone='Asia/Seoul')==1794153162.0
    finally: time.tzset()


def test_missing_iana_zone_data_blocks_instead_of_using_local_zone(monkeypatch):
    import ai_chem_input.submission.sge as sge
    def missing(name): raise ZoneInfoNotFoundError(name)
    monkeypatch.setattr(sge,'ZoneInfo',missing)
    with pytest.raises(InputError) as exc: timestamp('Mon Nov  9 00:52:42 2026','Asia/Seoul')
    assert exc.value.code=='SGE_TIMEZONE_UNKNOWN'


def test_oge_detail_and_single_accounting_summary_match_without_pe_taskid():
    detail=parse_detail((FIXTURES/'oge_6_2u7_qstat_detail.txt').read_bytes(),'Asia/Seoul')
    records=parse_accounting((FIXTURES/'oge_6_2u7_qacct_single.txt').read_bytes(),'Asia/Seoul')
    assert len(records)==1
    record=records[0]
    for key,expected in dict(job_id='1001',name='ac_'+'a'*32,owner='synthetic_owner',pe='mpi_32',slots=32,qsub_time=1794153162.0).items():
        assert record[key]==detail[key]==expected
    assert record['terminal'] and not detail['terminal']
    assert detail['token']=='a'*32 and detail['manifest']=='b'*64


@pytest.mark.parametrize('kind,key',[
    ('detail','job_number'),('detail','job_name'),('detail','owner'),
    ('detail','sge_o_workdir'),('detail','env_list'),('detail','submission_time'),('detail','parallel environment'),
    ('accounting','jobnumber'),('accounting','jobname'),('accounting','owner'),
    ('accounting','qsub_time'),('accounting','slots'),('accounting','granted_pe'),
])
def test_oge_required_fields_remain_required(kind,key):
    name='oge_6_2u7_qstat_detail.txt' if kind=='detail' else 'oge_6_2u7_qacct_single.txt'
    lines=(FIXTURES/name).read_bytes().splitlines(keepends=True)
    data=b''.join(line for line in lines if not line.startswith(key.encode()))
    parser=parse_detail if kind=='detail' else parse_accounting
    with pytest.raises(InputError): parser(data,'Asia/Seoul')


@pytest.mark.parametrize('slots,pe',[('1','mpi_32'),('32','other_pe')])
def test_oge_conflicting_masters_are_not_accepted(slots,pe):
    data=(FIXTURES/'oge_6_2u7_qacct_single.txt').read_bytes()
    conflict=data.replace(b'slots        32',('slots        '+slots).encode()).replace(b'granted_pe   mpi_32',('granted_pe   '+pe).encode())
    with pytest.raises(InputError): parse_accounting(data+conflict,'Asia/Seoul')


def test_oge_pe_task_needs_a_master_and_is_not_counted_as_a_second_job():
    master=(FIXTURES/'oge_6_2u7_qacct_single.txt').read_bytes()
    task=master.replace(b'slots        32',b'slots        1')+b'pe_taskid    1\n'
    with pytest.raises(InputError): parse_accounting(task,'Asia/Seoul')
    records=parse_accounting(master+task,'Asia/Seoul')
    assert len(records)==1 and records[0]['slots']==32
    assert parse_accounting(master+master,'Asia/Seoul')==parse_accounting(master,'Asia/Seoul')


def test_oge_array_task_is_not_a_single_job_summary():
    data=(FIXTURES/'oge_6_2u7_qacct_single.txt').read_bytes().replace(b'taskid       undefined',b'taskid       1')
    with pytest.raises(InputError): parse_accounting(data,'Asia/Seoul')
