#include "WalkRecorderComponent.h"

#include "Walkthrough.h"
#include "WalkDoor.h"
#include "WalkSun.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

namespace
{
	void SetCVarInt(const TCHAR* Name, int32 Value)
	{
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			V->Set(Value, ECVF_SetByCode);
		}
	}
}

UWalkRecorderComponent::UWalkRecorderComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PostPhysics;
}

void UWalkRecorderComponent::BeginPlay()
{
	Super::BeginPlay();
	if (ParseCommandLine())
	{
		Stage = 0;
	}
}

bool UWalkRecorderComponent::ParseCommandLine()
{
	const TCHAR* Cmd = FCommandLine::Get();
	FString Route;
	// bShouldStopOnSeparator = false: paths may contain commas.
	if (!FParse::Value(Cmd, TEXT("WalkOut="), OutDir, false) || !FParse::Value(Cmd, TEXT("WalkRoute="), Route, false))
	{
		return false;
	}
	FParse::Value(Cmd, TEXT("WalkFps="), Fps);
	FParse::Value(Cmd, TEXT("WalkFov="), Fov);
	FParse::Value(Cmd, TEXT("WalkWarm="), Warm);
	FParse::Value(Cmd, TEXT("WalkSub="), Sub);
	FParse::Value(Cmd, TEXT("WalkHour="), Hour);
	FParse::Value(Cmd, TEXT("WalkDay="), Day);
	FParse::Value(Cmd, TEXT("WalkEv="), Ev);
	FParse::Value(Cmd, TEXT("WalkWhite="), White);
	Fps = FMath::Max(Fps, 1);
	Sub = FMath::Max(Sub, 1);

	TArray<FString> Lines;
	if (!FFileHelper::LoadFileToStringArray(Lines, *Route))
	{
		UE_LOG(LogWalk, Error, TEXT("Walk: cannot read %s"), *Route);
		return false;
	}
	auto D = [](const FString& S) { return FCString::Atod(*S); };
	for (const FString& Line : Lines)
	{
		if (Line.StartsWith(TEXT("#")))
		{
			continue;
		}
		TArray<FString> F;
		Line.ParseIntoArrayWS(F);
		if (F.Num() == 8 && F[0] == TEXT("key"))
		{
			Keys.Add({D(F[1]), FVector(D(F[2]), D(F[3]), D(F[4])), FVector(D(F[5]), D(F[6]), D(F[7]))});
		}
		else if (F.Num() == 7 && F[0] == TEXT("door"))
		{
			Doors.Add({D(F[1]), FVector(D(F[2]), D(F[3]), D(F[4])), D(F[5]), F[6] == TEXT("open")});
		}
		else if (F.Num() == 6 && F[0] == TEXT("lamps"))
		{
			LampEvents.Add({D(F[1]), FVector(D(F[2]), D(F[3]), D(F[4])), float(D(F[5]))});
		}
		else if ((F.Num() == 3 || F.Num() == 4 || F.Num() == 6) && F[0] == TEXT("still"))
		{
			Stills.Add({D(F[1]), float(D(F[2])), F.Num() >= 4 ? float(D(F[3])) : -1.f,
				F.Num() == 6 ? float(D(F[4])) : 0.f, F.Num() == 6 ? float(D(F[5])) : -1.f});
		}
	}
	Keys.Sort([](const FKey& A, const FKey& B) { return A.T < B.T; });
	Doors.StableSort([](const FDoorEvent& A, const FDoorEvent& B) { return A.T < B.T; });
	LampEvents.StableSort([](const FLampEvent& A, const FLampEvent& B) { return A.T < B.T; });
	Stills.StableSort([](const FStill& A, const FStill& B) { return A.T < B.T; });
	if (Keys.Num() < 2)
	{
		UE_LOG(LogWalk, Error, TEXT("Walk: %s has fewer than 2 keys"), *Route);
		return false;
	}
	IFileManager::Get().MakeDirectory(*OutDir, true);
	UE_LOG(LogWalk, Warning, TEXT("Walk: %d keys, %d door events, %d stills, %.1f s"), Keys.Num(), Doors.Num(), Stills.Num(), Keys.Last().T);
	return true;
}

FVector UWalkRecorderComponent::Evaluate(double T, bool bLook) const
{
	// Cubic Hermite through the keys. Tangent at key J = (P[J+1] - P[J-1]) / (t[J+1] - t[J-1]), zero at the
	// ends and where two neighbouring keys are equal: two equal keys make the camera stop and start softly.
	const int32 N = Keys.Num();
	auto P = [&](int32 I) { return bLook ? Keys[I].Look : Keys[I].Eye; };
	if (T <= Keys[0].T)
	{
		return P(0);
	}
	if (T >= Keys[N - 1].T)
	{
		return P(N - 1);
	}
	int32 I = 0;
	while (I < N - 2 && Keys[I + 1].T <= T)
	{
		++I;
	}
	auto Tangent = [&](int32 J)
	{
		if (J == 0 || J == N - 1 || (P(J) - P(J - 1)).IsNearlyZero(1e-4) || (P(J + 1) - P(J)).IsNearlyZero(1e-4))
		{
			return FVector::ZeroVector;
		}
		return (P(J + 1) - P(J - 1)) / (Keys[J + 1].T - Keys[J - 1].T);
	};
	const double H = Keys[I + 1].T - Keys[I].T;
	const double S = H > 0.0 ? (T - Keys[I].T) / H : 1.0;
	const double S2 = S * S, S3 = S2 * S;
	return P(I) * (2 * S3 - 3 * S2 + 1) + Tangent(I) * (H * (S3 - 2 * S2 + S))
		+ P(I + 1) * (-2 * S3 + 3 * S2) + Tangent(I + 1) * (H * (S3 - S2));
}

void UWalkRecorderComponent::ApplyEventsUpTo(double T, bool bSnap)
{
	for (; Sun && NextLamp < LampEvents.Num() && LampEvents[NextLamp].T <= T; ++NextLamp)
	{
		Sun->SetOnlyRoomAt(FromModel(LampEvents[NextLamp].At), LampEvents[NextLamp].Level);
	}
	for (; NextDoor < Doors.Num() && Doors[NextDoor].T <= T; ++NextDoor)
	{
		const FDoorEvent& E = Doors[NextDoor];
		const FVector At = FromModel(E.At);
		for (TActorIterator<AWalkDoor> It(GetWorld()); It; ++It)
		{
			// The hinge may stand at floor level while the leaf carries its height: accept either.
			const FVector H = It->GetActorLocation();
			const double LeafZ = (It->Leaf && It->Leaf->GetStaticMesh()) ? It->Leaf->Bounds.Origin.Z : H.Z;
			const double Dz = FMath::Min(FMath::Abs(H.Z - At.Z), FMath::Abs(LeafZ - At.Z));
			if (FVector::Dist2D(H, At) <= E.Radius * 100.0 && Dz < 150.0)
			{
				It->bOpen = E.bOpen;
				if (bSnap)
				{
					It->Snap();
				}
			}
		}
	}
}

void UWalkRecorderComponent::Pose(double T)
{
	AActor* Owner = GetOwner();
	const FVector Eye = FromModel(Evaluate(T, false));
	const FVector Look = FromModel(Evaluate(T, true));
	// Move the actor so that the camera (wherever it sits on the pawn) lands on the eye point.
	const FVector Offset = Camera ? Camera->GetComponentLocation() - Owner->GetActorLocation() : FVector::ZeroVector;
	Owner->SetActorLocation(Eye - Offset, false, nullptr, ETeleportType::TeleportPhysics);
	FRotator R = (Look - Eye).Rotation();
	R.Roll = 0.f;
	APawn* Pawn = Cast<APawn>(Owner);
	if (AController* C = Pawn ? Pawn->GetController() : nullptr)
	{
		C->SetControlRotation(R);
	}
	else if (Camera)
	{
		Camera->SetWorldRotation(R);
	}
}

void UWalkRecorderComponent::Begin()
{
	AActor* Owner = GetOwner();
	Camera = Owner->FindComponentByClass<UCameraComponent>();
	if (TActorIterator<AWalkSun> It(GetWorld()); It)
	{
		Sun = *It;
	}
	if (ACharacter* Ch = Cast<ACharacter>(Owner))
	{
		Ch->GetCharacterMovement()->DisableMovement();
	}
	Owner->SetActorEnableCollision(false);       // the camera passes through glass and doorways on fly-ins
	if (Camera)
	{
		Camera->SetFieldOfView(Fov);
	}
	if (Sun)
	{
		if (Day > 0)
		{
			Sun->SetDay(Day);
		}
		if (Hour >= 0.f)
		{
			Sun->SetHour(Hour);
		}
		Sun->SetExposure(Ev);
		Sun->SetDayWhite(White);
	}
	if (GEngine)
	{
		GEngine->ClearOnScreenDebugMessages();
		GEngine->bEnableOnScreenDebugMessages = false;
	}
	// Motion blur smears AI restyling and frame-by-frame scrubbing; off for recordings.
	SetCVarInt(TEXT("r.MotionBlurQuality"), 0);
	ApplyEventsUpTo(-0.001, true);
	FApp::SetUseFixedTimeStep(true);
	FApp::SetFixedDeltaTime(1.0 / (double(Fps) * Sub));
	Pose(Stills.Num() ? Stills[0].T : 0.0);
}

void UWalkRecorderComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (Stage < 0)
	{
		return;
	}
	if (Stage == 0)
	{
		Clock += DeltaTime;
		if (Clock < 1.5f)
		{
			return;          // the pawn is not possessed yet on the first ticks
		}
		Begin();
		Stage = 1;
		Frame = 0;
		return;
	}
	if (Stage == 1)
	{
		Pose(Stills.Num() ? Stills[0].T : 0.0);
		if (++Frame < FMath::RoundToInt(Warm * Fps * Sub))
		{
			return;
		}
		Frame = 0;
		LastFrame = FMath::CeilToInt(Keys.Last().T * Fps);
		Stage = Stills.Num() ? 4 : 2;
		StillIndex = -1;
		StillPhase = 2;
	}
	if (Stage == 4)
	{
		TickStills();
		return;
	}
	if (Stage == 2)
	{
		// Frame counts engine frames; every Sub-th one is saved. The screenshot is taken at the end of this
		// frame, without the UI.
		const double T = Frame / (double(Fps) * Sub);
		ApplyEventsUpTo(T, false);
		Pose(T);
		if (Frame % Sub == 0)
		{
			const int32 Saved = Frame / Sub;
			FScreenshotRequest::RequestScreenshot(OutDir / FString::Printf(TEXT("frame_%05d.png"), Saved), false, false);
			if (Saved % 240 == 0)
			{
				UE_LOG(LogWalk, Warning, TEXT("Walk: frame %d of %d"), Saved, LastFrame);
			}
		}
		if (++Frame > LastFrame * Sub)
		{
			Stage = 3;
		}
		return;
	}
	if (Stage == 3 && ++Frame > LastFrame * Sub + 30)
	{
		UE_LOG(LogWalk, Warning, TEXT("Walk: done, %d frames"), LastFrame + 1);
		Quit();
	}
}

void UWalkRecorderComponent::SetPathTracing(bool bOn)
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || bPathTracing == bOn)
	{
		return;
	}
	bPathTracing = bOn;
	if (bOn)
	{
		// Needs r.PathTracing=True in DefaultEngine.ini. Denoiser: the NNEDenoiser plugin (OIDN is Windows only).
		SetCVarInt(TEXT("r.PathTracing.SamplesPerPixel"), 256);
		SetCVarInt(TEXT("r.PathTracing.Denoiser"), 1);
		SetCVarInt(TEXT("r.PathTracing.ProgressDisplay"), 0);
	}
	VC->EngineShowFlags.SetPathTracing(bOn);
}

void UWalkRecorderComponent::TickStills()
{
	// One picture per still line: go to route time t (doors as in the walk), hold 4 s of game time for the
	// doors, Lumen and the exposure (8 s after a change of hour), then save; or path trace for the given real
	// seconds first.
	if (StillPhase == 2)
	{
		if (StillIndex >= 0 && ++StillTicks < 6)
		{
			return;          // the screenshot is written at the end of a frame: keep the view a few frames
		}
		SetPathTracing(false);
		if (++StillIndex >= Stills.Num())
		{
			UE_LOG(LogWalk, Warning, TEXT("Walk: stills done"));
			Quit();
			return;
		}
		const FStill& S = Stills[StillIndex];
		const bool bNewHour = Sun && S.Hour >= 0.f && !FMath::IsNearlyEqual(S.Hour, Sun->GetHour());
		if (bNewHour)
		{
			Sun->SetHour(S.Hour);
		}
		if (Sun && S.White > 0.f)
		{
			Sun->SetExposure(S.Ev);
			Sun->SetDayWhite(S.White);
		}
		ApplyEventsUpTo(S.T, true);
		Pose(S.T);
		StillPhase = 0;
		StillTicks = -FMath::RoundToInt((bNewHour ? 8.f : 4.f) * Fps * Sub);
		return;
	}
	const FStill& S = Stills[StillIndex];
	Pose(S.T);
	if (StillPhase == 0)
	{
		if (++StillTicks < 0)
		{
			return;
		}
		if (S.PathTrace > 0.f)
		{
			SetPathTracing(true);
			StillStart = FPlatformTime::Seconds();
			StillPhase = 1;
			UE_LOG(LogWalk, Warning, TEXT("Walk: path tracing still %d of %d (t %.2f)"), StillIndex + 1, Stills.Num(), S.T);
			return;
		}
	}
	else if (StillPhase == 1 && FPlatformTime::Seconds() - StillStart < S.PathTrace)
	{
		return;              // real seconds: the path tracer accumulates samples per rendered frame
	}
	FString Name = FString::Printf(TEXT("still_%05d"), FMath::RoundToInt(S.T * 100.0));
	if (S.Hour >= 0.f)
	{
		Name += FString::Printf(TEXT("_h%04d"), FMath::RoundToInt(S.Hour * 100.f));
	}
	FScreenshotRequest::RequestScreenshot(OutDir / (Name + TEXT(".png")), false, false);
	UE_LOG(LogWalk, Warning, TEXT("Walk: saved %s"), *Name);
	StillPhase = 2;
	StillTicks = 0;
}

void UWalkRecorderComponent::Quit()
{
	Stage = -1;
	FApp::SetUseFixedTimeStep(false);
	APawn* Pawn = Cast<APawn>(GetOwner());
	UKismetSystemLibrary::QuitGame(this, Pawn ? Cast<APlayerController>(Pawn->GetController()) : nullptr, EQuitPreference::Quit, false);
}
