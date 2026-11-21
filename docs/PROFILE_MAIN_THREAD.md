# Main-thread profile: Switch 2 (fnv_prof.nro, -O2)

Console run 2026-11-20 of port/switch2/fnv_prof (the shipping -O2 build plus the shadow call stack, FNV_PROFILE_STACK). Intervals 5-9 are gameplay (24-47 fps, mean 31; renderer waiting for the game 85-91% of the time); 0-4 were start-up and loading and are left out. Only ~50 s of gameplay: treat individual percentages below ~0.2% as noise. Regenerate: python3 tools/prof_report.py fnv_prof.txt --log fnv.log --intervals 5-9

- **Samples:** 48902 of the main thread at 1 kHz (49 s), intervals 5-9; fps in those intervals 24-47 (mean 30.7).
- **Where:** 73.3% in recompiled game code (3725 functions seen), 26.7% in platform-layer calls (D3D9, files, sound, waits), 0.0% outside any guest code.
- **Self time** = the function was the innermost recompiled function on the shadow call stack; **inclusive** = it was anywhere on the stack. Percentages are of all main-thread samples unless marked "of guest".

## How concentrated is it?

Functions, largest self time first, needed to cover a share of the time spent in recompiled code (platform layer and idle excluded):

| share of guest time | functions |
|---:|---:|
| 50% | 63 |
| 80% | 290 |
| 90% | 590 |
| 95% | 964 |
| 99% | 1824 |

The top 200 functions cover 73.9% of guest time; the top 20 cover 28.7%, the top 50 45.2%.
Counting platform-layer calls as functions too: 50% = 49, 80% = 228, 90% = 496 of all samples.

## By subsystem (self time)

Classified from the decomp unit and the demangled name (tools/prof_report.py GROUPS; first match wins, so treat the split as approximate).

| subsystem | self % of all | % of guest | functions | biggest |
|---|---:|---:|---:|---|
| platform layer (PAL) | 26.7 | - | 83 | PAL Sleep 5.7%, PAL IDirect3DDevice9::SetVertexShaderConstantF 2.1%, PAL WaitForSingleObject 2.0% |
| renderer submit / shaders / lighting | 16.2 | 22.0 | 468 | fnv_00b7dab0::RX::UpdateRenderPass 1.6%, PrepareShaderAndStreams 0.9%, DrawGeometryPass 0.9% |
| other / unnamed | 14.0 | 19.1 | 897 | fnv_00e90b10::FUN_00e90b10_shell::GetTextureData 1.1%, PassState::ApplyPassState 0.8%, FUN_00e89250_cls::DispatchSlots 0.6% |
| math / transform | 8.0 | 10.9 | 115 | NiTransform::operator* 1.4%, NiMatrix3::operator* 0.8%, Point3Offset::ProjectileLaunched 0.6% |
| scene graph update | 7.2 | 9.8 | 84 | NiPSysBombModifier::Update_00c2e670 2.1%, NiNode::UpdateDownwardPass 1.1%, BoundUpdateOperations::UpdateBounds 0.7% |
| containers / strings / refcount | 6.0 | 8.2 | 205 | Owner_44e550::j_GetFirst_LockFreeMapInterface_Lo 2.7%, FUN_0044e010_class::LockFreeMap_MarkedPointer_Se 0.5%, NiTMapBase<class DFALL<class NiTMapItem<unsigned 0.4% |
| culling / visibility | 5.0 | 6.8 | 65 | FUN_00a5dbe0_shell::NiNode_OnVisible 1.0%, WorkerS694a0::NiCullingProcess_DoCulling 1.0%, NiBound::WhichSide 0.5% |
| AI / actors | 4.4 | 6.0 | 460 | FUN_0044b8d0_Class::ProcessIteration 1.2%, FUN_0096b050_shell::UpdateLowProcesses 0.6%, ProcessCommands 0.4% |
| physics (Havok) | 4.2 | 5.7 | 447 | fnv_00c65b00::CollisionSync::bhkCollisionObject_ 0.3%, SampledHeightRayCastView::hkpSampledHeightFieldS 0.2%, GapSolver::hkpGsk_getClosestFeature 0.2% |
| world / forms / extra data | 3.4 | 4.6 | 470 | CExpression::Eval 0.3%, BGSSaveGameBuffer::SaveData 0.3%, ScriptRunner::GetNextLine 0.2% |
| animation / skinning | 2.3 | 3.2 | 174 | NiD3DShaderConstantMap::ConfigureShaderConstantM 0.6%, BlendTransformInterpolator::NiBlendTransformInte 0.2%, ConstantMap::NiD3DShaderConstantMap_SetDefinedCo 0.1% |
| scripts / events | 1.0 | 1.4 | 30 | Runner::RunScript 0.2%, ScriptLocals::GetVariable 0.1%, Script::GetReferencedObject 0.1% |
| audio | 0.5 | 0.7 | 68 | ThisClsAda::BSAudioManager_SetVoiceState 0.1%, BSWin32GameSound::SetVolume_00aed660 0.1%, FalloutAudio::UpdateRegionSounds 0.0% |
| UI / menus | 0.5 | 0.7 | 107 | FUN_0044d5c0_Cls::ThreadSpecificInterfaceManager 0.2%, Tile_ValueSortFunc 0.0%, FUN_00424940_shell::InterfaceManager_GetMenuMode 0.0% |
| memory / allocator | 0.3 | 0.4 | 41 | BSMapBase<unsigned long, class ScrapHeapBuffer * 0.1%, MemoryManager::Game_DoHeapAlloc 0.0%, FNV_MemoryManager::MemoryManager_Deallocate 0.0% |
| I/O / streaming / tasks | 0.3 | 0.4 | 94 | BSAtomicCompareExchange 0.1%, FUN_00aee580_cls::UpdateStreamBuffer 0.0%, FUN_00afdc00_cls::BSArchive_IsFileEntryInArchive 0.0% |

## Largest inclusive times (where the frame goes)

| inclusive % | self % | address | function |
|---:|---:|---|---|
| 100.0 | 0.01 | 0086a850 | WinMain_0086a850 |
| 100.0 | 0.00 | 00ecc35d | ? |
| 100.0 | 0.09 | 0086e650 | FrameUpdate::MainLoop::Main_OnIdle |
| 45.5 | 0.03 | 0086ff70 | fnv_0086ff70::Main86::Main_Swap |
| 43.7 | 0.00 | 008706b0 | fnv_008706b0::FUN_008706b0_shell::Main_DrawWorld |
| 43.7 | 0.04 | 00870bd0 | fnv_00870bd0::RenderCoordinator::TESMain_DrawWorldStandard |
| 38.0 | 0.05 | 00873200 | fnv_00873200::MainView::TESMain_DrawWorld_DrawScene |
| 32.7 | 0.47 | 00b994f0 | fnv_00b994f0::BSBatchRenderer_RenderPassImmediately |
| 26.5 | 0.86 | 00b98e80 | DrawGeometryPass |
| 20.8 | 0.01 | 00b66520 | ShaderAccumulatorLocal::ApplyRenderMode |
| 19.9 | 0.02 | 00b63770 | RenderAccumulator::BSShaderAccumulator_RenderBatches |
| 19.8 | 0.19 | 00b9a120 | BSBatchRenderer_RenderNextRenderPass |
| 19.1 | 0.01 | 00b65ae0 | fnv_00b65ae0::BSShaderAccumulator_FinishAccumulating_Standard_PreResolveDepth |
| 15.5 | 0.01 | 0086f940 | fnv_0086f940::PlayerUpdateState::Main_OnIdle_UpdatePlayer |
| 13.0 | 0.01 | 00b66570 | ShaderAccumulatorLocal::BSShaderAccumulator_FinishAccumulatingPostResolveDepth |
| 12.9 | 0.00 | 00b65c60 | fnv_00b65c60::BSShaderAccumulator_FinishAccumulating_Standard_PostResolveDepth |
| 11.8 | 0.00 | 008705d0 | fnv_008705d0::TESMain_PostSwapProcess |
| 11.6 | 0.01 | 00b650c0 | ViewX::UpdatePasses |
| 11.6 | 0.01 | 0086f6a0 | fnv_0086f6a0::FUN_0086f6a0_shell::Main_UpdateNonRenderSafeAITasks |
| 11.5 | 0.23 | 00b9af60 | BSBatchRenderer::UpdateVisibility |
| 10.3 | 1.14 | 00a5dd70 | NiNode::UpdateDownwardPass |
| 9.3 | 0.04 | 00493bd0 | AnimSwap::Animation_UpdateSceneGraphNoController |
| 9.2 | 1.56 | 00b7dab0 | fnv_00b7dab0::RX::UpdateRenderPass |
| 8.9 | 0.00 | 0093bea0 | FUN_0093bea0_cls::PlayerCharacter_HandlePositionPlayerRequest |
| 8.9 | 0.00 | 0093c200 | fnv_0093c200::MatchPlayer::PlayerCharacter_PositionPlayer |
| 8.3 | 0.01 | 00c3dbf0 | IOManager::UpdateQueue |
| 7.9 | 0.00 | 00453dc0 | ReloadManager::AttachScene |
| 7.6 | 0.03 | 0096c970 | FUN_0096c970_shell::ProcessLists_ParallelUpdateAnimationScenegraph |
| 7.5 | 0.01 | 00493930 | C00493930::Animation_UpdateQueuedScenegraph |
| 7.5 | 0.22 | 00e7eb00 | NiD3DPass::ApplyRenderStateChanges |
| 7.5 | 0.12 | 00a59f90 | NiAVObject::UpdateDownwardPass |
| 7.4 | 0.01 | 00446e40 | ModelLoader_UpdateSecondaryQueueCallback |
| 7.3 | 0.01 | 00448cc0 | fnv_00448cc0::ModelLoaderStand_00448cc0::ProcessQueuedTasks |
| 7.3 | 0.36 | 00c4ee90 | HostV::BSCullingProcess_Process |
| 7.3 | 1.16 | 0044b8d0 | FUN_0044b8d0_Class::ProcessIteration |
| 7.3 | 0.99 | 00a5dbe0 | FUN_00a5dbe0_shell::NiNode_OnVisible |
| 6.9 | 0.03 | 00c4f070 | NiCullingProcess::BSCullingProcess_Process_00c4f070 |
| 6.9 | 0.00 | 00c3dfa0 | IOManager::LoadQueuedPriority |
| 6.9 | 0.01 | 00b6bee0 | BSShaderUtil_AccumulateScene |
| 6.6 | 0.30 | 0093e860 | TickPlayer::PlayerCharacter_Update |
| 6.5 | 0.04 | 00b5f9b0 | fnv_00b5f9b0::ShadowSceneCuller::ShadowSceneNode_OnVisible |
| 6.1 | 0.04 | 00a59c60 | FUN_00a59c60_cls::NiAVObject_Update |
| 6.1 | 0.19 | 00b7d200 | Host200::ShadowLightShader_SetupGeometryTextures |
| 5.9 | 0.97 | 00a694e0 | WorkerS694a0::NiCullingProcess_DoCulling |
| 5.7 | 5.66 | f0000360 | PAL Sleep |
| 5.6 | 0.32 | 004eff50 | NiAVObject::UpdateTimeControllers |
| 5.3 | 0.14 | 00be2170 | BSShader_ApplyTextureStages |
| 5.1 | 0.80 | 00e7ea00 | PassState::ApplyPassState |
| 5.0 | 0.01 | 00552570 | fnv_00552570::TESObjectCELL_RunQueuedParticleUpdates |
| 4.9 | 0.09 | 005526f0 | TESObjectCELL_UpdateParticlesOnly |
| 4.7 | 0.01 | 00c1ad90 | ParticleDownwardPassReceiver::NiParticleSystem_UpdateDownwardPass |
| 4.1 | 2.70 | 0044e550 | Owner_44e550::j_GetFirst_LockFreeMapInterface_LockFreeMap_PAVTESObjectREFR_V_NiPointer_VQueuedReference_QAE_NI |
| 4.0 | 0.13 | 00455490 | fnv_00455490::QuestCellUpdate::TES_RunScripts |
| 4.0 | 0.00 | 0086f670 | FUN_0086f670_shell::Main_RunScripts |
| 3.8 | 0.19 | 00b99390 | SetShaderPass |
| 3.6 | 0.02 | 00c271c0 | SpawnedController::NiPSysUpdateCtlr_Update |
| 3.5 | 0.57 | 00e826d0 | NiD3DShaderConstantMap::ConfigureShaderConstantMap |
| 3.5 | 0.01 | 00c1ae40 | NiParticleSystem::UpdateSystem |
| 3.5 | 0.11 | 00c1b260 | NiParticleSystem::Do_UpdateSystem |
| 3.5 | 1.35 | 0062c250 | NiTransform::operator* |

## Top 200 functions by self time

| # | self % | cum % of guest | incl % | address | function | subsystem | top callers (share of its self) |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 5.66 |  | 5.7 | f0000360 | PAL Sleep | platform layer (PAL) | 00c3dfa0 100%, 0040fca0 0% |
| 2 | 2.70 | 3.7 | 4.1 | 0044e550 | Owner_44e550::j_GetFirst_LockFreeMapInterface_LockFreeMap_PAVTESObjectREFR_V_NiPointer_VQueuedRefere | containers / strings / refcount | 0044b8d0 100% |
| 3 | 2.13 |  | 2.1 | f0001fe0 | PAL IDirect3DDevice9::SetVertexShaderConstantF | platform layer (PAL) | 00e826d0 51%, 00b7c750 28% |
| 4 | 2.11 | 6.6 | 2.2 | 00c2e670 | NiPSysBombModifier::Update_00c2e670 | scene graph update | 00c1b260 100% |
| 5 | 2.05 |  | 2.0 | f0000670 | PAL WaitForSingleObject | platform layer (PAL) | 00aa8740 61%, 004424e0 38% |
| 6 | 1.70 |  | 1.7 | f0000650 | PAL InterlockedIncrement | platform layer (PAL) | 00e870c0 66%, 0040b460 15% |
| 7 | 1.56 | 8.7 | 9.2 | 00b7dab0 | fnv_00b7dab0::RX::UpdateRenderPass | renderer submit / shaders / lighting | 00b98e80 97%, 00b99110 2% |
| 8 | 1.43 |  | 1.4 | f00020d0 | PAL IDirect3DDevice9::SetPixelShaderConstantF | platform layer (PAL) | 00e826d0 100% |
| 9 | 1.42 |  | 1.4 | f0000060 | PAL TlsGetValue | platform layer (PAL) | 0044d5b0 68%, 00c85750 9% |
| 10 | 1.36 |  | 1.4 | f0000660 | PAL InterlockedDecrement | platform layer (PAL) | 00e870c0 70%, 004019a0 15% |
| 11 | 1.35 | 10.5 | 3.5 | 0062c250 | NiTransform::operator* | math / transform | 00a68bf0 85%, 00a86530 6% |
| 12 | 1.16 | 12.1 | 7.3 | 0044b8d0 | FUN_0044b8d0_Class::ProcessIteration | AI / actors | 00448cc0 100% |
| 13 | 1.14 | 13.7 | 10.3 | 00a5dd70 | NiNode::UpdateDownwardPass | scene graph update | 00a5dd70 94%, 00493bd0 2% |
| 14 | 1.10 | 15.2 | 2.3 | 00e90b10 | fnv_00e90b10::FUN_00e90b10_shell::GetTextureData | other / unnamed | 00e7ea00 100% |
| 15 | 1.08 |  | 1.1 | f00004d0 | PAL GetFileAttributesA | platform layer (PAL) | 00ecbe7c 100% |
| 16 | 1.03 |  | 1.0 | f0001e50 | PAL IDirect3DDevice9::SetSamplerState | platform layer (PAL) | 00e7ea00 79%, 00e910a0 17% |
| 17 | 0.99 | 16.5 | 7.3 | 00a5dbe0 | FUN_00a5dbe0_shell::NiNode_OnVisible | culling / visibility | 00c4ee90 70%, 00b4e490 20% |
| 18 | 0.97 | 17.8 | 5.9 | 00a694e0 | WorkerS694a0::NiCullingProcess_DoCulling | culling / visibility | 00c4ee90 99%, 00a59e00 1% |
| 19 | 0.89 | 19.1 | 2.9 | 00e812f0 | PrepareShaderAndStreams | renderer submit / shaders / lighting | 00b98e80 98%, 00b99110 1% |
| 20 | 0.88 |  | 0.9 | f00000c0 | PAL EnterCriticalSection | platform layer (PAL) | 00e90b10 67%, 00a5bdd0 13% |
| 21 | 0.86 | 20.2 | 26.5 | 00b98e80 | DrawGeometryPass | renderer submit / shaders / lighting | 00b994f0 100% |
| 22 | 0.85 | 21.4 | 3.2 | 00e870c0 | CompactEnabledEntries | renderer submit / shaders / lighting | 00e87200 100% |
| 23 | 0.81 |  | 0.8 | f0001e10 | PAL IDirect3DDevice9::SetTexture | platform layer (PAL) | 00e88a20 99% |
| 24 | 0.80 | 22.5 | 5.1 | 00e7ea00 | PassState::ApplyPassState | other / unnamed | 00e7eb00 100% |
| 25 | 0.78 | 23.5 | 0.8 | 0043f8d0 | NiMatrix3::operator* | math / transform | 0062c250 98%, 00a7de40 1% |
| 26 | 0.77 |  | 0.8 | f0002040 | PAL IDirect3DDevice9::SetStreamSource | platform layer (PAL) | 00e812f0 100% |
| 27 | 0.72 | 24.5 | 1.1 | 00b70820 | UpdateWaterTint | renderer submit / shaders / lighting | 00b78a90 98%, 00b71360 2% |
| 28 | 0.70 |  | 0.7 | f0000350 | PAL LeaveCriticalSection | platform layer (PAL) | 00e90b10 82%, 00e74120 3% |
| 29 | 0.66 | 25.4 | 1.1 | 00e892d0 | fnv_00e892d0::FUN_00e892d0_cls::NiD3DTextureStageGroup_SetAllStageSamplers | renderer submit / shaders / lighting | 00e89410 99% |
| 30 | 0.66 |  | 0.7 | f0002080 | PAL IDirect3DDevice9::SetIndices | platform layer (PAL) | 00e812f0 99% |
| 31 | 0.65 | 26.3 | 0.7 | 00c2df20 | BoundUpdateOperations::UpdateBounds | scene graph update | 00c1b260 100% |
| 32 | 0.62 | 27.2 | 1.1 | 0096b050 | FUN_0096b050_shell::UpdateLowProcesses | AI / actors | 0096d810 100% |
| 33 | 0.60 |  | 0.6 | f0001d90 | PAL IDirect3DDevice9::SetRenderState | platform layer (PAL) | 00e88780 100% |
| 34 | 0.58 | 28.0 | 0.9 | 00e89250 | FUN_00e89250_cls::DispatchSlots | other / unnamed | 00e89410 100% |
| 35 | 0.57 | 28.7 | 3.5 | 00e826d0 | NiD3DShaderConstantMap::ConfigureShaderConstantMap | animation / skinning | 00b7dab0 76%, 00bc9a50 8% |
| 36 | 0.56 | 29.5 | 1.0 | 00e74840 | fnv_00e74840::Renderer::DrawGeometry | renderer submit / shaders / lighting | 00a71d70 100% |
| 37 | 0.55 | 30.3 | 0.7 | 00439e90 | Point3Offset::ProjectileLaunched | math / transform | 0062c250 74%, 00c39270 25% |
| 38 | 0.55 | 31.0 | 0.6 | 00a7f3f0 | Sphere::NiBound_Merge | math / transform | 00a86530 76%, 00a5dd70 15% |
| 39 | 0.53 | 31.7 | 1.3 | 004b6100 | NiBound::WhichSide | culling / visibility | 00a694e0 100% |
| 40 | 0.51 |  | 0.5 | f0001f20 | PAL IDirect3DDevice9::DrawIndexedPrimitive | platform layer (PAL) | 00e74840 78%, 00e745a0 20% |
| 41 | 0.50 | 32.4 | 0.8 | 004b6160 | NiPlane::Distance | math / transform | 004b6100 97%, 0043d450 1% |
| 42 | 0.48 |  | 0.5 | f0000f60 | PAL D3DXMatrixMultiplyTranspose | platform layer (PAL) | 00b7c750 83%, 00e83db0 17% |
| 43 | 0.47 | 33.1 | 32.7 | 00b994f0 | fnv_00b994f0::BSBatchRenderer_RenderPassImmediately | renderer submit / shaders / lighting | 00b9a120 74%, 00b9af60 16% |
| 44 | 0.47 |  | 0.5 | f0000690 | PAL GetCurrentThreadId | platform layer (PAL) | 0040fc90 95%, 0043b460 4% |
| 45 | 0.47 | 33.7 | 0.5 | 0044e010 | FUN_0044e010_class::LockFreeMap_MarkedPointer_SetMark | containers / strings / refcount | 006ecba0 51%, 0044e550 45% |
| 46 | 0.46 |  | 0.5 | f0000640 | PAL InterlockedCompareExchange | platform layer (PAL) | 0043b460 81%, 0040fbe0 17% |
| 47 | 0.45 |  | 0.4 | f0001580 | PAL IDirectSound8::CreateSoundBuffer | platform layer (PAL) | 00aec530 96%, 00af0630 2% |
| 48 | 0.43 | 34.3 | 1.6 | 004b4880 | NiTransform::CalculateInverse | math / transform | 00c4c2d0 87%, 00c6bbb0 9% |
| 49 | 0.43 | 34.9 | 0.4 | 00416870 | FUN_00416870_t::SetComponents | other / unnamed | 00439e90 38%, 004a3760 26% |
| 50 | 0.42 | 35.4 | 0.4 | 00ec419d | ? (inside ?AddOrUpdate@FUN_00ec2f00_cls@@QAEXPAXI@Z) | other / unnamed | 00ec43fb 100% |
| 51 | 0.42 | 36.0 | 0.4 | 00e88930 | S_00e88930_Cls::SetItemValue | other / unnamed | 00e89250 70%, 00e7e940 21% |
| 52 | 0.41 | 36.6 | 1.8 | 00b64020 | ProcessCommands | AI / actors | 00b63f10 100% |
| 53 | 0.40 | 37.1 | 1.8 | 00b78a90 | UpdateLightPass | renderer submit / shaders / lighting | 00b7dab0 100% |
| 54 | 0.40 | 37.7 | 1.4 | 00a86530 | NiScreenLODData::UpdateScreenBound | math / transform | 00a80710 100% |
| 55 | 0.39 | 38.2 | 0.4 | 00b98b20 | CompareSortPassesByDepth | other / unnamed | 00b99630 100% |
| 56 | 0.39 |  | 0.4 | f0001b10 | PAL IDirect3DDevice9::Present | platform layer (PAL) | 00e7ccd0 100% |
| 57 | 0.38 | 38.7 | 0.4 | 00853130 | NiTMapBase<class DFALL<class NiTMapItem<unsigned int, class CombatThreatRecord_nitmapbase *>>, unsig | containers / strings / refcount | 00b99c90 31%, 00846c90 20% |
| 58 | 0.37 | 39.2 | 0.4 | 00529000 | FUN_00529000_cls::LockFreeMap_LockFreeMapInterface_ClearReferencedNodes | containers / strings / refcount | 0044e550 85%, 0044de40 8% |
| 59 | 0.36 | 39.7 | 1.3 | 0044d5b0 | TlsGetValue_ | other / unnamed | 0044d5c0 100% |
| 60 | 0.36 | 40.2 | 0.7 | 00b67be0 | Shader::GetPasses | renderer submit / shaders / lighting | 00b64020 100% |
| 61 | 0.36 | 40.7 | 0.4 | 004b4500 | NiMatrix3::operator* | math / transform | 0062c250 71%, 004b4880 22% |
| 62 | 0.36 | 41.2 | 7.3 | 00c4ee90 | HostV::BSCullingProcess_Process | culling / visibility | 00a5dbe0 93%, 00c46f60 3% |
| 63 | 0.35 | 41.7 | 0.6 | 00e6fbb0 | XRenderer::NiDX9Renderer_SetModelTransform | renderer submit / shaders / lighting | 00b7c750 82%, 00bca980 7% |
| 64 | 0.35 | 42.1 | 1.3 | 00c387f0 | OccShape::BSMultiBoundAABB_WithinFrustum | culling / visibility | 00b5bbe0 62%, 00c46f60 38% |
| 65 | 0.34 | 42.6 | 1.9 | 00a80710 | NiGeometry::UpdateWorldBound | scene graph update | 00a59f90 68%, 00a59d80 20% |
| 66 | 0.33 | 43.0 | 0.3 | 0049da80 | NiCamera::ClassifyPoint | culling / visibility | 00c387f0 99% |
| 67 | 0.32 | 43.5 | 5.6 | 004eff50 | NiAVObject::UpdateTimeControllers | scene graph update | 00a5dd70 72%, 00a59f90 26% |
| 68 | 0.31 | 43.9 | 2.7 | 00b4e490 | fnv_00b4e490::FadeNodeObj::BSFadeNode_OnVisible | culling / visibility | 00a694e0 96%, 00c4ee90 3% |
| 69 | 0.31 | 44.3 | 0.9 | 00e88780 | FUN_00e88780_Class::SetIndexedValue | other / unnamed | 00e879e0 21%, 00b97ff0 12% |
| 70 | 0.31 | 44.8 | 0.4 | 00401050 | `vector ctor iterator' | other / unnamed | 004768c0 89%, 00a33570 5% |
| 71 | 0.30 | 45.2 | 1.6 | 00593db0 | CExpression::Eval | world / forms / extra data | 005e1550 100% |
| 72 | 0.30 | 45.6 | 6.6 | 0093e860 | TickPlayer::PlayerCharacter_Update | AI / actors | 0086f940 100% |
| 73 | 0.29 | 46.0 | 0.3 | 00593870 | FNVTokenParser::ParseToken | other / unnamed | 00593db0 100% |
| 74 | 0.29 | 46.4 | 0.3 | 006815c0 | BSSimpleList<class InventoryStackRecord *>::GetItem | containers / strings / refcount | 00476a80 20%, 00401050 18% |
| 75 | 0.29 | 46.8 | 2.3 | 00c65b00 | fnv_00c65b00::CollisionSync::bhkCollisionObject_NitohkTransform | physics (Havok) | 00c81e30 91%, 00c6b670 8% |
| 76 | 0.29 | 47.2 | 0.3 | 0044de40 | MapMarkerData::SetVisible | culling / visibility | 0044b8d0 98%, 0044c640 1% |
| 77 | 0.28 | 47.5 | 0.4 | 004a3760 | NiPosData::ComputePositionAtTime | math / transform | 0062c250 78%, 004b4880 17% |
| 78 | 0.28 | 47.9 | 3.3 | 00a68bf0 | NiAVObject::UpdateWorldLoc | scene graph update | 00a68c60 81%, 00c65b00 12% |
| 79 | 0.28 | 48.3 | 0.5 | 00e910a0 | FUN_00e910a0_shell::NiDX9RenderState_SetSamplerState | renderer submit / shaders / lighting | 00e892d0 93%, 00e7ea00 1% |
| 80 | 0.27 | 48.7 | 0.3 | 004b6190 | NiPoint3::Dot | math / transform | 004b6160 99% |
| 81 | 0.27 | 49.0 | 0.3 | 00559450 | Modelloader_GetReferencedThis | other / unnamed | 0044e550 35%, 0043b230 18% |
| 82 | 0.26 | 49.4 | 1.8 | 00b7c750 | FUN_00b7c750_cls::ShadowLightShader_SetupGeometryOpt_WorldViewProj | renderer submit / shaders / lighting | 00b7dab0 78%, 00b7dde0 22% |
| 83 | 0.26 | 49.7 | 0.4 | 00865ce0 | BGSSaveGameBuffer::SaveData | world / forms / extra data | 00865570 86%, 00865ff0 8% |
| 84 | 0.25 | 50.1 | 0.3 | 0044dec0 | ClearLowBit | other / unnamed | 0044e550 98%, 006662a0 2% |
| 85 | 0.25 | 50.4 | 1.2 | 00a5e0b0 | NiNode::UpdateTransformAndBounds | scene graph update | 00a5e0b0 75%, 0087cf50 25% |
| 86 | 0.25 | 50.8 | 0.4 | 00b7c0e0 | ShaderStageManager::ShadowLightShader_SetNormalMap | renderer submit / shaders / lighting | 00b7d200 100% |
| 87 | 0.23 | 51.1 | 0.3 | 00d24b50 | SampledHeightRayCastView::hkpSampledHeightFieldShape_castRayInternal | physics (Havok) | 00d260d0 88%, 00d26080 11% |
| 88 | 0.23 | 51.4 | 0.8 | 004768c0 | NiMatrix3::Transpose | math / transform | 004b4880 100% |
| 89 | 0.23 | 51.7 | 11.5 | 00b9af60 | BSBatchRenderer::UpdateVisibility | renderer submit / shaders / lighting | 00b650c0 100% |
| 90 | 0.23 | 52.0 | 2.9 | 005e0d20 | Runner::RunScript | scripts / events | 005e2590 100% |
| 91 | 0.22 | 52.3 | 1.6 | 0044d5c0 | FUN_0044d5c0_Cls::ThreadSpecificInterfaceManager_GetInterface | UI / menus | 00449f80 100% |
| 92 | 0.22 | 52.6 | 0.4 | 00e71fe0 | GeometryPacketBuilder::PrepareGeometryPacket | other / unnamed | 00e812f0 100% |
| 93 | 0.22 | 52.9 | 7.5 | 00e7eb00 | NiD3DPass::ApplyRenderStateChanges | renderer submit / shaders / lighting | 00be2170 81%, 00b7dde0 8% |
| 94 | 0.21 | 53.2 | 1.2 | 00a71d70 | RenderTriStrips | renderer submit / shaders / lighting | 00b98e80 100% |
| 95 | 0.21 | 53.5 | 0.2 | 00c206b0 | UpdateRotationAngles | scene graph update | 00c1b260 100% |
| 96 | 0.21 | 53.8 | 1.4 | 0040fbf0 | FUN_0040fbf0_shell::BSSpinLock_Lock | containers / strings / refcount | 0043a010 26%, 00410220 18% |
| 97 | 0.21 | 54.1 | 0.4 | 00e7de90 | E7DE90Owner::ApplyPairToState | other / unnamed | 00b7c0e0 36%, 00b7c0a0 28% |
| 98 | 0.21 | 54.4 | 0.4 | 00daad40 | GapSolver::hkpGsk_getClosestFeature | physics (Havok) | 00dac450 62%, 00dabca0 37% |
| 99 | 0.20 | 54.6 | 0.2 | 00a7fdd0 | NiBound::Update | math / transform | 00a86530 85%, 00a80710 11% |
| 100 | 0.20 | 54.9 | 0.4 | 006ecba0 | GO::SetTaggedPointer | other / unnamed | 0044e550 99% |
| 101 | 0.20 | 55.2 | 0.2 | 00b7c320 | ApplyRenderModeState | renderer submit / shaders / lighting | 00b98e80 100% |
| 102 | 0.20 | 55.5 | 0.6 | 0040fc90 | GarbageCollector::QueryCurrentThread | other / unnamed | 0040fbf0 98% |
| 103 | 0.19 | 55.7 | 0.3 | 005e13a0 | ScriptRunner::GetNextLine | world / forms / extra data | 005e0d20 100% |
| 104 | 0.19 | 56.0 | 0.6 | 00c39270 | OBBox::BSMultiBoundAABB_GetVertices | culling / visibility | 00c387f0 100% |
| 105 | 0.19 | 56.2 | 0.3 | 00d16300 | SweepSpace::hkp3AxisSweep_castRay | physics (Havok) | 00cfab30 97%, 00cbf860 2% |
| 106 | 0.19 | 56.5 | 0.2 | 00b49070 | _inflate_fast | other / unnamed | 00b44000 100% |
| 107 | 0.19 | 56.8 | 6.1 | 00b7d200 | Host200::ShadowLightShader_SetupGeometryTextures | renderer submit / shaders / lighting | 00b98e80 97% |
| 108 | 0.19 | 57.0 | 19.8 | 00b9a120 | BSBatchRenderer_RenderNextRenderPass | renderer submit / shaders / lighting | 00b63770 100% |
| 109 | 0.19 | 57.3 | 0.2 | 00e890c0 | LightSlots::NiD3DTextureStageGroup_SetSamplerState | renderer submit / shaders / lighting | 00e7de90 95%, 00e7def0 2% |
| 110 | 0.19 | 57.5 | 2.8 | 00b7dde0 | BloodDraw_b7dde0::ShadowLightShader_Setup_ADT_Opt | renderer submit / shaders / lighting | 00b98e80 100% |
| 111 | 0.19 | 57.8 | 2.3 | 005e1550 | ScriptRunner::EvaluateLine | world / forms / extra data | 005e0d20 100% |
| 112 | 0.19 | 58.0 | 3.8 | 00b99390 | SetShaderPass | renderer submit / shaders / lighting | 00b994f0 100% |
| 113 | 0.18 | 58.3 | 0.2 | 00b795b0 | ShaderS::ApplyFogAndAlpha | renderer submit / shaders / lighting | 00b7dab0 100% |
| 114 | 0.18 | 58.5 | 0.4 | 00be1f90 | fnv_00be1f90::SetFromGlobalManager | other / unnamed | 00b99390 96%, 00c03d80 3% |
| 115 | 0.18 | 58.8 | 0.3 | 00b7ba70 | S00b7ba70_Updater::ShadowLightShader_SetupGeometryConstants_AmbientEmittance | renderer submit / shaders / lighting | 00b7dab0 100% |
| 116 | 0.18 | 59.0 | 2.1 | 00e89410 | FUN_00e89410_Class::GetItemByIndex | other / unnamed | 00e7eb00 100% |
| 117 | 0.18 | 59.3 | 0.3 | 00a40c10 | BlendTransformInterpolator::NiBlendTransformInterpolator_BlendValues | animation / skinning | 00a41110 100% |
| 118 | 0.17 | 59.5 | 1.7 | 00449f80 | LockFreeMap_GetInterface_0 | containers / strings / refcount | 0044b8d0 98% |
| 119 | 0.17 |  | 0.2 | f0000f90 | PAL D3DXVec3Normalize | platform layer (PAL) | 00b78a90 80%, 00b7c7b0 20% |
| 120 | 0.17 | 59.7 | 1.5 | 00c4c2d0 | fnv_00c4c2d0::BSUtilities_GetInverseWorldMatrix | other / unnamed | 00b7dab0 80%, 00b7dde0 20% |
| 121 | 0.17 | 60.0 | 0.8 | 00c8e160 | fnv_00c8e160::This160::bhkRigidBody_ApplyHardKeyframe | physics (Havok) | 00c65b00 96% |
| 122 | 0.17 | 60.2 | 0.5 | 00410220 | fnv_00410220::FUN_00410220_shell::BaseExtraList_GetExtraData | world / forms / extra data | 00418800 35%, 0041b370 13% |
| 123 | 0.17 | 60.4 | 1.0 | 00e88a20 | FUN_00e88a20_cls::NiD3DRenderState_SetTexture | renderer submit / shaders / lighting | 00e7ea00 98% |
| 124 | 0.16 | 60.6 | 0.6 | 00b5c5c0 | CheckBoundAndChildren | other / unnamed | 00b5c5c0 78%, 00b5dac0 21% |
| 125 | 0.16 | 60.9 | 0.2 | 00476a80 | _dummy_476a80::NiTransform_NiTransform | math / transform | 0062c250 100% |
| 126 | 0.16 | 61.1 | 0.2 | 0062c430 | TESHavokUtilities_ConsolidateSimIslands | other / unnamed | 009781d0 84%, 008885e0 13% |
| 127 | 0.16 | 61.3 | 0.2 | 00e8eeb0 | GraphicsRenderer::HasPendingPackets | renderer submit / shaders / lighting | 00e71fe0 97% |
| 128 | 0.16 | 61.5 | 0.2 | 0043d450 | FUN_0043d450_Owner::NiAVObject_GetWorldBound | math / transform | 00a694e0 99% |
| 129 | 0.15 |  | 0.2 | f0000fa0 | PAL D3DXVec3TransformNormal | platform layer (PAL) | 00b78a90 71%, 00b7c7b0 28% |
| 130 | 0.15 | 61.7 | 0.2 | 0049e390 | IsApproximatelyEqual | other / unnamed | 0049e2f0 100% |
| 131 | 0.15 | 61.9 | 3.3 | 00c81e30 | BlendTransformDetail::BlendLocal::bhkBlendCollisionObject_hktoNiTransform | physics (Havok) | 00c817d0 97% |
| 132 | 0.15 | 62.1 | 3.3 | 005ac1e0 | Script::Run | world / forms / extra data | 0060d4d0 74%, 00565870 22% |
| 133 | 0.15 | 62.3 | 0.1 | 00d58ee0 | MatchShape::hkpConvexVerticesShape_getSupportingVertexImpl | physics (Havok) | 00daad40 73%, 00dafe70 25% |
| 134 | 0.15 | 62.5 | 0.1 | 00c602e0 | SimpleColorModifierEntries::UpdateParticleColors | scene graph update | 00c1b260 100% |
| 135 | 0.14 | 62.7 | 5.3 | 00be2170 | BSShader_ApplyTextureStages | renderer submit / shaders / lighting | 00b7d200 97% |
| 136 | 0.14 | 62.9 | 0.3 | 00e745a0 | Se745_StandinRenderer::NiDX9Renderer_RenderTriShape2 | renderer submit / shaders / lighting | 00a74600 100% |
| 137 | 0.14 | 63.1 | 0.5 | 00e83db0 | ConstantMap::NiD3DShaderConstantMap_SetDefinedConstant | animation / skinning | 00e826d0 100% |
| 138 | 0.13 | 63.3 | 0.6 | 00ed1165 | ? | other / unnamed | 00ed11de 100% |
| 139 | 0.13 | 63.5 | 0.2 | 005a9140 | ScriptLocals::GetVariable | scripts / events | 005ac7a0 100% |
| 140 | 0.13 | 63.6 | 0.2 | 005ac4f0 | Script::GetReferencedObject | scripts / events | 005accb0 78%, 005ac7a0 13% |
| 141 | 0.13 | 63.8 | 0.2 | 006fea70 | FUN_006fea70_Class::SetValue | other / unnamed | 006fea70 100% |
| 142 | 0.13 | 64.0 | 0.1 | 00c2f010 | NiPSysAgeDeathModifier::UpdateAges | scene graph update | 00c1b260 100% |
| 143 | 0.13 | 64.2 | 4.0 | 00455490 | fnv_00455490::QuestCellUpdate::TES_RunScripts | scripts / events | 0086f670 100% |
| 144 | 0.13 | 64.3 | 0.4 | 00ada5d0 | ThisClsAda::BSAudioManager_SetVoiceState | audio | 00adddd0 87%, 00adf080 13% |
| 145 | 0.13 | 64.5 | 0.2 | 00439ef0 | FUN_00439ef0_class::SubtractIntoVector | math / transform | 00c39270 89% |
| 146 | 0.13 | 64.7 | 0.1 | 00401460 | ? (inside ?CopyFromDehydrationStage@DehydrationStageCopyAccess@@QAEXPAVTESForm@@@Z) | world / forms / extra data | 00865ce0 74%, 00593db0 13% |
| 147 | 0.12 |  | 0.1 | f00006c0 | PAL SetLastError | platform layer (PAL) | 00ed1165 100% |
| 148 | 0.12 | 64.8 | 0.2 | 004a3e00 | fnv_004a3e00::NI2HK | physics (Havok) | 00c65b00 97% |
| 149 | 0.12 | 65.0 | 0.4 | 00457990 | NiPoint3::ComputeMagnitude | math / transform | 004a0c10 62%, 00b67be0 27% |
| 150 | 0.12 | 65.2 | 7.5 | 00a59f90 | NiAVObject::UpdateDownwardPass | scene graph update | 00a5dd70 90%, 00c1ad90 5% |
| 151 | 0.12 | 65.3 | 0.1 | 008256d0 | BSSimpleList<class InventoryStackRecord *>::IsEmpty | containers / strings / refcount | 005ac4f0 40%, 005ae2e0 27% |
| 152 | 0.12 | 65.5 | 0.2 | 004a0bd0 | NiPoint3::GetNegatedVector | math / transform | 004b4880 92% |
| 153 | 0.12 | 65.7 | 0.9 | 004f0380 | AnimationInterpolatorNode::BSTransCon_UpdateAllButTarget | animation / skinning | 004f0040 100% |
| 154 | 0.11 | 65.8 | 0.1 | 00a1e380 | BSMapBase<unsigned long, class ScrapHeapBuffer *>::GetAt | memory / allocator | 00a0a220 30%, 00ada330 30% |
| 155 | 0.11 | 66.0 | 0.2 | 00476980 | FUN_00476980_S::NiMatrix3_NiMatrix3 | math / transform | 004768c0 100% |
| 156 | 0.11 | 66.1 | 0.3 | 00be1ff0 | NiD3DShader_SetupGeometryAlphaBlending | renderer submit / shaders / lighting | 00b98e80 87%, 00bc8ed0 9% |
| 157 | 0.11 | 66.3 | 0.5 | 0043b460 | BSAtomicCompareExchange | I/O / streaming / tasks | 0040fbf0 96% |
| 158 | 0.11 | 66.4 | 3.5 | 00c1b260 | NiParticleSystem::Do_UpdateSystem | scene graph update | 00c1ae40 100% |
| 159 | 0.11 | 66.6 | 0.3 | 00e86f40 | S_00e86f40_Arr::NiTObjectArray_NiShaderConstantMapEntry_SetAt | containers / strings / refcount | 00e870c0 100% |
| 160 | 0.11 | 66.7 | 0.2 | 0043b230 | fnv_0043b230::NiObjectNET_GetControllers | scene graph update | 004eff50 63%, 006fa860 11% |
| 161 | 0.11 | 66.9 | 0.3 | 00561730 | S00561730_Vector::hkVector4_equals4 | physics (Havok) | 005616d0 66%, 00561800 30% |
| 162 | 0.11 | 67.0 | 0.4 | 00b99c90 | AddPassToGroup | renderer submit / shaders / lighting | 00b64020 75%, 00b9abc0 23% |
| 163 | 0.11 |  | 0.1 | f0001fc0 | PAL IDirect3DDevice9::SetVertexShader | platform layer (PAL) | 00be1f90 98% |
| 164 | 0.10 | 67.2 | 0.5 | 00bca760 | fnv_00bca760::PassShader::ApplyToRenderer | renderer submit / shaders / lighting | 00b98e80 100% |
| 165 | 0.10 | 67.3 | 0.1 | 006532c0 | NiObject_b::NiObject_IsKindOf_006532c0 | other / unnamed | 00653290 74%, 0043b300 22% |
| 166 | 0.10 | 67.5 | 0.5 | 00b99630 | FUN_00b99630_shell::SortList | containers / strings / refcount | 00b99a10 100% |
| 167 | 0.10 | 67.6 | 0.1 | 0040fba0 | RecursiveSpinLock::BSSpinLock_Unlock | containers / strings / refcount | 0043a010 49%, 00410220 24% |
| 168 | 0.10 | 67.7 | 0.2 | 004579e0 | NiSqrt_004579e0 | math / transform | 00457990 94% |
| 169 | 0.10 | 67.9 | 2.9 | 00a68c60 | NiAVObject::UpdateWorldData | scene graph update | 00a5dd70 67%, 00a59f90 12% |
| 170 | 0.10 | 68.0 | 0.1 | 0043b4a0 | NiNode::GetAt | scene graph update | 00456fc0 29%, 0045c9e0 16% |
| 171 | 0.10 | 68.1 | 0.3 | 00e879e0 | FUN_00e879e0_Class::NiD3DRenderState_SetModelTransform | renderer submit / shaders / lighting | 00e6fbb0 98% |
| 172 | 0.10 | 68.3 | 0.1 | 00a3aa10 | fnv_00a3aa10::UpdateMorphWeights | animation / skinning | 00a3b080 100% |
| 173 | 0.10 | 68.4 | 0.2 | 00e7e940 | fnv_00e7e940::SamplerStandIn::BindTexture | other / unnamed | 00e7ea00 100% |
| 174 | 0.10 |  | 0.1 | f00016a0 | PAL IDirectSoundBuffer8::GetStatus | platform layer (PAL) | 00aee580 100% |
| 175 | 0.10 |  | 0.1 | f0000f70 | PAL D3DXVec3TransformCoord | platform layer (PAL) | 00b78a90 85%, 00b78ef0 13% |
| 176 | 0.09 | 68.5 | 0.2 | 00b97f20 | BSRenderState_SetAlphaTestFuncRef | renderer submit / shaders / lighting | 00be20b0 98% |
| 177 | 0.09 | 68.7 | 2.0 | 00b63f10 | FUN_00b63f10_CH::DispatchHandler | other / unnamed | 00c4f1d0 100% |
| 178 | 0.09 | 68.8 | 2.3 | 00b7b450 | BSShaderPass::ShadowLightShader_SetupPassConstants | renderer submit / shaders / lighting | 00b99390 100% |
| 179 | 0.09 | 68.9 | 0.1 | 00b99a90 | fnv_00b99a90::Thing::AddNode | other / unnamed | 00b99c90 98% |
| 180 | 0.09 | 69.0 | 2.5 | 00565870 | fnv_00565870::FUN_00565870_shell::TESObjectREFR_RunScript | world / forms / extra data | 0054c740 64%, 00978550 29% |
| 181 | 0.09 | 69.2 | 0.1 | 00a6cd60 | NiTimeController::ComputeScaledTime | animation / skinning | 00a36250 93% |
| 182 | 0.09 | 69.3 | 0.1 | 004019b0 | sqrt_004019b0 | math / transform | 004579e0 100% |
| 183 | 0.09 | 69.4 | 3.4 | 00c817d0 | C817D0Cls::UpdateNodeState | other / unnamed | 00a5dd70 98% |
| 184 | 0.09 | 69.6 | 0.1 | 00c03010 | AccumulateLightColor | renderer submit / shaders / lighting | 00b7ba70 100% |
| 185 | 0.09 | 69.7 | 0.1 | 004b46a0 | NiMatrix3::Inverse | math / transform | 008b42e0 100% |
| 186 | 0.09 | 69.8 | 4.9 | 005526f0 | TESObjectCELL_UpdateParticlesOnly | world / forms / extra data | 005526f0 93%, 00552570 7% |
| 187 | 0.09 | 69.9 | 0.1 | 004f0000 | FUN_004f0000_shell::NiAVObject_GetHasPropertyController | other / unnamed | 004eff50 98% |
| 188 | 0.09 | 70.0 | 100.0 | 0086e650 | FrameUpdate::MainLoop::Main_OnIdle | other / unnamed | 0086a850 100% |
| 189 | 0.09 |  | 0.1 | f00020b0 | PAL IDirect3DDevice9::SetPixelShader | platform layer (PAL) | 00be1f90 95%, 00bca760 5% |
| 190 | 0.08 | 70.2 | 0.1 | 00a26b40 | NiFloatKey::InterpolatePosition | other / unnamed | 00a3fdb0 49%, 00a3c6d0 34% |
| 191 | 0.08 |  | 0.1 | f0000620 | PAL ReleaseSemaphore | platform layer (PAL) | 00442550 71%, 00c44cd0 20% |
| 192 | 0.08 | 70.3 | 0.1 | 00a4ff00 | NiQuaternion::FastNormalize | math / transform | 00a6e330 54%, 00a50f60 46% |
| 193 | 0.08 | 70.4 | 0.1 | 00b66b80 | FUN_00b66b80_cls::BSShaderPPLightingProperty_GetSpecularLODFade | renderer submit / shaders / lighting | 00b70820 98% |
| 194 | 0.08 | 70.5 | 0.1 | 00408840 | std::abs | other / unnamed | 0049e390 70%, 00408820 25% |
| 195 | 0.08 | 70.6 | 0.1 | 0043b480 | NiNode::GetNumChildren | scene graph update | 0087d030 62%, 0045b070 12% |
| 196 | 0.08 | 70.7 | 0.1 | 00b9dae0 | ShadowSceneLight::BoundWithinLightRadius | math / transform | 00b5dac0 49%, 00b9f6a0 38% |
| 197 | 0.08 |  | 0.1 | f00001a0 | PAL GetLastError | platform layer (PAL) | 00ed1165 100% |
| 198 | 0.08 | 70.8 | 0.5 | 00ec43fb | ? (inside ?AddOrUpdate@FUN_00ec2f00_cls@@QAEXPAXI@Z) | other / unnamed | 0093e860 74%, 00834260 10% |
| 199 | 0.08 | 70.9 | 1.6 | 0060d4d0 | TESQuest::RunScript | scripts / events | 00455490 100% |
| 200 | 0.08 | 71.0 | 0.3 | 0040b460 | NiAtomicIncrement_0040b460 | other / unnamed | 0040f6e0 71%, 005e2590 24% |

