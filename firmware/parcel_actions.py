def command(r,s,cmd,now,pot):
    if cmd=='DUMP':
        print('@D,{},{},{},{},{},{},{},{},{},{},0'.format(r.trip,r.duration,r.mode,r.limit,r.peak,r.counts[0],r.counts[1],r.counts[2],r.n,len(r.events)))
        for i in range(len(r.events)):
            print('@R,{},{},{},{},{}'.format(r.trip,*r.record(i)))
        print('@DONE,{}'.format(r.trip))
        return
    if cmd=='MUTE':
        s[0]=not s[0]
        result='MUTED' if s[0] else 'SOUND_ON'
    elif cmd=='SAVE':
        result='RAM_ONLY'
    else:
        result=r.cmd(cmd,now,pot)
    print('@A,'+result)
