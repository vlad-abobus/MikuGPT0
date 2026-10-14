3D-панда для окна pywebview (view3d.html).

Нужны три GLB-файла с анимацией и скелетом:
  panda_idle.glb  - поза/анимация покоя
  panda_talk.glb  - разговор
  panda_yell.glb  - крик/эмоция

Эти файлы уже сгенерированы из mdels/*.fbx конвертером FBX2glTF
(Facebook, https://github.com/facebookincubator/FBX2glTF):

  FBX2glTF.exe -i mdels\Happy_Idle.fbx -o models\panda_idle -b
  FBX2glTF.exe -i mdels\Talking.fbx    -o models\panda_talk -b
  FBX2glTF.exe -i mdels\Yelling.fbx    -o models\panda_yell -b

Важно: конвертировать нужно ИМЕННО с сохранением анимации и скелета.
Простые онлайн-конвертеры часто отдают только статичную сетку без анимации.
