#include "WalkCharacter.h"

#include "Walkthrough.h"
#include "WalkDoor.h"
#include "WalkRecorderComponent.h"
#include "WalkSun.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"

namespace
{
	// Horizontal field of view across the wider side of the screen. 75 is like a 24 mm lens on full frame,
	// 90 like a real-estate wide angle.
	const float Fovs[] = {75.f, 90.f};

	struct FQuality { const TCHAR* Name; float ScreenPercent; int32 Scalability; int32 Shadows; bool bHardwareRT; };
	const FQuality Qualities[] = {
		{TEXT("Fast"), 60.f, 1, 1, false},
		{TEXT("Balanced"), 80.f, 2, 2, true},
		{TEXT("High"), 100.f, 3, 3, true},
		{TEXT("Cinematic"), 200.f, 4, 4, true},     // recordings only: very slow to walk in
	};
	constexpr int32 KeyQualities = 3;               // P cycles Fast, Balanced, High
}

AWalkCharacter::AWalkCharacter()
{
	PrimaryActorTick.bCanEverTick = false;
	// A 1.75 m person: capsule half height 87.5 cm, radius 30 cm (fits 80 cm doorways and narrow halls).
	GetCapsuleComponent()->InitCapsuleSize(30.f, 87.5f);
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(GetCapsuleComponent());
	Camera->SetRelativeLocation(FVector(0.f, 0.f, EyeHeight - 87.5f));
	Camera->bUsePawnControlRotation = true;
	Camera->SetFieldOfView(Fovs[0]);
	bUseControllerRotationYaw = true;
	Recorder = CreateDefaultSubobject<UWalkRecorderComponent>(TEXT("Recorder"));

	UCharacterMovementComponent* Moves = GetCharacterMovement();
	Moves->MaxWalkSpeed = WalkSpeed;
	Moves->MaxStepHeight = 30.f;                    // stairs of up to 30 cm risers
	Moves->BrakingDecelerationWalking = 1200.f;
	Moves->bCanWalkOffLedges = true;
}

void AWalkCharacter::BeginPlay()
{
	Super::BeginPlay();
	Camera->SetRelativeLocation(FVector(0.f, 0.f, EyeHeight - GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
	if (TActorIterator<AWalkSun> It(GetWorld()); It)
	{
		Sun = *It;
	}
	LoadSpots();
	int32 Level = 2;
	FParse::Value(FCommandLine::Get(), TEXT("WalkQuality="), Level);
	ApplyQuality(Level);
	if (!Recorder->IsRecording())
	{
		Say(TEXT("W A S D walk, E door, 1-9 spots, F view, L lamps, T hour, P quality, R path trace"));
	}
}

void AWalkCharacter::Say(const FString& Text) const
{
	if (GEngine && !Recorder->IsRecording())
	{
		GEngine->AddOnScreenDebugMessage(1, 4.f, FColor::White, Text);
	}
}

void AWalkCharacter::LoadSpots()
{
	// Written by import_manifest.py in Unreal units: {"spots": [{"name", "loc": [x, y, z], "yaw"}]}.
	FString Text;
	const FString File = FPaths::ProjectContentDir() / TEXT("Data/spots.json");
	if (!FFileHelper::LoadFileToString(Text, *File))
	{
		return;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		return;
	}
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (!Root->TryGetArrayField(TEXT("spots"), List))
	{
		return;
	}
	for (const TSharedPtr<FJsonValue>& V : *List)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		const TArray<TSharedPtr<FJsonValue>>& L = O->GetArrayField(TEXT("loc"));
		if (L.Num() == 3)
		{
			Spots.Add({O->GetStringField(TEXT("name")), FVector(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber()),
				float(O->GetNumberField(TEXT("yaw")))});
		}
	}
}

UInputAction* AWalkCharacter::MakeAction(const TCHAR* Name, bool bAxis2D)
{
	UInputAction* A = NewObject<UInputAction>(this, Name);
	A->ValueType = bAxis2D ? EInputActionValueType::Axis2D : EInputActionValueType::Boolean;
	Actions.Add(Name, A);
	return A;
}

void AWalkCharacter::BuildInput()
{
	if (Mapping)
	{
		return;
	}
	Mapping = NewObject<UInputMappingContext>(this, TEXT("WalkKeys"));
	UInputAction* MoveAction = MakeAction(TEXT("Move"), true);
	// Axis2D: x = strafe, y = forward. Forward keys swizzle their 1D value into y.
	auto MapMove = [&](FKey Key, bool bSwizzle, bool bNegate)
	{
		FEnhancedActionKeyMapping& M = Mapping->MapKey(MoveAction, Key);
		if (bSwizzle)
		{
			M.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(Mapping));
		}
		if (bNegate)
		{
			M.Modifiers.Add(NewObject<UInputModifierNegate>(Mapping));
		}
	};
	MapMove(EKeys::W, true, false);
	MapMove(EKeys::S, true, true);
	MapMove(EKeys::D, false, false);
	MapMove(EKeys::A, false, true);
	MapMove(EKeys::Up, true, false);
	MapMove(EKeys::Down, true, true);
	MapMove(EKeys::Right, false, false);
	MapMove(EKeys::Left, false, true);
	MapMove(EKeys::Gamepad_Left2D, false, false);

	FEnhancedActionKeyMapping& Mouse = Mapping->MapKey(MakeAction(TEXT("Look"), true), EKeys::Mouse2D);
	UInputModifierNegate* FlipY = NewObject<UInputModifierNegate>(Mapping);
	FlipY->bX = false;
	FlipY->bZ = false;
	Mouse.Modifiers.Add(FlipY);

	Mapping->MapKey(MakeAction(TEXT("Run"), false), EKeys::LeftShift);
	Mapping->MapKey(MakeAction(TEXT("Use"), false), EKeys::E);
	Mapping->MapKey(MakeAction(TEXT("Fov"), false), EKeys::F);
	Mapping->MapKey(MakeAction(TEXT("Lamps"), false), EKeys::L);
	UInputAction* Up = MakeAction(TEXT("HourUp"), false);
	Mapping->MapKey(Up, EKeys::T);
	Mapping->MapKey(Up, EKeys::RightBracket);
	Mapping->MapKey(MakeAction(TEXT("HourDown"), false), EKeys::LeftBracket);
	Mapping->MapKey(MakeAction(TEXT("Quality"), false), EKeys::P);
	Mapping->MapKey(MakeAction(TEXT("PathTrace"), false), EKeys::R);
	const FKey Digits[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six,
		EKeys::Seven, EKeys::Eight, EKeys::Nine};
	for (int32 i = 0; i < 9; ++i)
	{
		Mapping->MapKey(MakeAction(*FString::Printf(TEXT("Spot%d"), i), false), Digits[i]);
	}
}

void AWalkCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	BuildInput();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Sub->ClearAllMappings();
			Sub->AddMappingContext(Mapping, 0);
		}
	}
}

void AWalkCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	BuildInput();
	UEnhancedInputComponent* In = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!In)
	{
		UE_LOG(LogWalk, Error, TEXT("Set the Enhanced Input component class in Project Settings > Input"));
		return;
	}
	In->BindAction(Actions[TEXT("Move")], ETriggerEvent::Triggered, this, &AWalkCharacter::Move);
	In->BindAction(Actions[TEXT("Look")], ETriggerEvent::Triggered, this, &AWalkCharacter::Look);
	In->BindAction(Actions[TEXT("Run")], ETriggerEvent::Started, this, &AWalkCharacter::RunOn);
	In->BindAction(Actions[TEXT("Run")], ETriggerEvent::Completed, this, &AWalkCharacter::RunOff);
	In->BindAction(Actions[TEXT("Use")], ETriggerEvent::Started, this, &AWalkCharacter::Use);
	In->BindAction(Actions[TEXT("Fov")], ETriggerEvent::Started, this, &AWalkCharacter::CycleFov);
	In->BindAction(Actions[TEXT("Lamps")], ETriggerEvent::Started, this, &AWalkCharacter::ToggleLamps);
	In->BindAction(Actions[TEXT("HourUp")], ETriggerEvent::Started, this, &AWalkCharacter::HourUp);
	In->BindAction(Actions[TEXT("HourDown")], ETriggerEvent::Started, this, &AWalkCharacter::HourDown);
	In->BindAction(Actions[TEXT("Quality")], ETriggerEvent::Started, this, &AWalkCharacter::CycleQuality);
	In->BindAction(Actions[TEXT("PathTrace")], ETriggerEvent::Started, this, &AWalkCharacter::TogglePathTracing);
	for (int32 i = 0; i < 9; ++i)
	{
		In->BindAction(Actions[*FString::Printf(TEXT("Spot%d"), i)], ETriggerEvent::Started, this, &AWalkCharacter::GoTo, i);
	}
}

void AWalkCharacter::Move(const FInputActionValue& Value)
{
	if (Recorder->IsRecording() || !Controller)
	{
		return;
	}
	const FVector2D V = Value.Get<FVector2D>();
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), V.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), V.X);
}

void AWalkCharacter::Look(const FInputActionValue& Value)
{
	if (Recorder->IsRecording())
	{
		return;
	}
	const FVector2D V = Value.Get<FVector2D>();
	AddControllerYawInput(V.X);
	AddControllerPitchInput(V.Y);
}

void AWalkCharacter::RunOn()
{
	GetCharacterMovement()->MaxWalkSpeed = RunSpeed;
}

void AWalkCharacter::RunOff()
{
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
}

void AWalkCharacter::Use()
{
	// Trace from the eye along the view; the door actor owns the hit leaf or glass component.
	const FVector From = Camera->GetComponentLocation();
	const FVector To = From + GetControlRotation().Vector() * UseDistance;
	FHitResult Hit;
	FCollisionQueryParams Params(TEXT("WalkUse"), true, this);
	if (GetWorld()->LineTraceSingleByChannel(Hit, From, To, ECC_Visibility, Params))
	{
		if (AWalkDoor* Door = Cast<AWalkDoor>(Hit.GetActor()))
		{
			Door->Toggle();
		}
	}
}

void AWalkCharacter::CycleFov()
{
	FovIndex = (FovIndex + 1) % UE_ARRAY_COUNT(Fovs);
	Camera->SetFieldOfView(Fovs[FovIndex]);
	Say(FString::Printf(TEXT("Field of view %.0f degrees"), Fovs[FovIndex]));
}

void AWalkCharacter::ToggleLamps()
{
	if (Sun)
	{
		Sun->ToggleLamps();
		Say(Sun->AreLampsOn() ? TEXT("Lamps on") : TEXT("Lamps off"));
	}
}

void AWalkCharacter::HourUp()
{
	if (Sun)
	{
		Sun->SetHour(Sun->GetHour() + 1.f);
		Say(FString::Printf(TEXT("%02d:00, day %d (Lumen settles in a few seconds)"), FMath::RoundToInt(Sun->GetHour()), Sun->GetDay()));
	}
}

void AWalkCharacter::HourDown()
{
	if (Sun)
	{
		Sun->SetHour(Sun->GetHour() - 1.f);
		Say(FString::Printf(TEXT("%02d:00, day %d"), FMath::RoundToInt(Sun->GetHour()), Sun->GetDay()));
	}
}

void AWalkCharacter::CycleQuality()
{
	ApplyQuality((FMath::Min(Quality, KeyQualities - 1) + 1) % KeyQualities);
}

void AWalkCharacter::ApplyQuality(int32 Level)
{
	Quality = FMath::Clamp(Level, 0, int32(UE_ARRAY_COUNT(Qualities)) - 1);
	const FQuality& Q = Qualities[Quality];
	APlayerController* PC = Cast<APlayerController>(GetController());
	auto Cmd = [&](const FString& C) { UKismetSystemLibrary::ExecuteConsoleCommand(this, C, PC); };
	Cmd(FString::Printf(TEXT("r.ScreenPercentage %.0f"), Q.ScreenPercent));
	for (const TCHAR* Group : {TEXT("sg.GlobalIlluminationQuality"), TEXT("sg.ReflectionQuality"),
		TEXT("sg.PostProcessQuality"), TEXT("sg.EffectsQuality"), TEXT("sg.FoliageQuality")})
	{
		Cmd(FString::Printf(TEXT("%s %d"), Group, Q.Scalability));
	}
	Cmd(FString::Printf(TEXT("sg.ShadowQuality %d"), Q.Shadows));
	Cmd(FString::Printf(TEXT("r.Lumen.HardwareRayTracing %d"), Q.bHardwareRT ? 1 : 0));
	// The preset is applied for this session only (nothing is written to GameUserSettings.ini), so a test
	// run never leaves a slow or a blurry preset behind.
	Say(FString::Printf(TEXT("Quality: %s (%.0f %% resolution%s)"), Q.Name, Q.ScreenPercent, Q.bHardwareRT ? TEXT(", ray tracing") : TEXT("")));
}

void AWalkCharacter::TogglePathTracing()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || Recorder->IsRecording())
	{
		return;
	}
	if (!bPathTracing)
	{
		// The path tracer renders like an offline renderer (all bounces, true reflections and soft shadows).
		// Stand still: moving the camera restarts the samples.
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("r.PathTracing.SamplesPerPixel")))
		{
			V->Set(256, ECVF_SetByCode);
		}
		if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(TEXT("r.PathTracing.Denoiser")))
		{
			V->Set(1, ECVF_SetByCode);
		}
		VC->EngineShowFlags.SetPathTracing(true);
		bPathTracing = true;
		Say(TEXT("Path tracing: wait for the samples, then R to save"));
		return;
	}
	const FString Dir = FPaths::ProjectSavedDir() / TEXT("Stills");
	IFileManager::Get().MakeDirectory(*Dir, true);
	const FString File = Dir / (TEXT("Still_") + FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")) + TEXT(".png"));
	if (GEngine)
	{
		GEngine->ClearOnScreenDebugMessages();
	}
	FScreenshotRequest::RequestScreenshot(File, false, false);
	// Switch back a moment later: the screenshot is taken at the end of the frame.
	FTimerHandle Back;
	GetWorldTimerManager().SetTimer(Back, [this, File]()
	{
		if (UGameViewportClient* V = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
		{
			V->EngineShowFlags.SetPathTracing(false);
		}
		bPathTracing = false;
		Say(TEXT("Saved ") + FPaths::ConvertRelativePathToFull(File));
	}, 0.3f, false);
}

void AWalkCharacter::GoTo(int32 Index)
{
	if (!Spots.IsValidIndex(Index) || Recorder->IsRecording())
	{
		return;
	}
	const FSpot& S = Spots[Index];
	// Spots are eye positions on the floor (z = floor): stand the capsule on it.
	SetActorLocation(S.Loc + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f), false, nullptr,
		ETeleportType::TeleportPhysics);
	if (Controller)
	{
		Controller->SetControlRotation(FRotator(0.f, S.Yaw, 0.f));
	}
	Say(S.Name);
}
